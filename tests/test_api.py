import io
import json
import struct


def test_health_and_auth(client):
    assert client.get('/api/v1/health').json()['ok'] is True
    assert client.get('/api/v1/session').json()['authenticated'] is False
    assert client.get('/api/v1/projects').status_code == 401
    assert client.post('/api/v1/session/login', json={'password': 'wrong'}).status_code == 401
    result = client.post('/api/v1/session/login', json={'password': 'test-password-never-production'})
    assert result.status_code == 200
    assert client.get('/api/v1/session').json()['authenticated'] is True
    assert client.post('/api/v1/projects', json={'title': 'Blocked without CSRF'}).status_code == 403


def test_project_crud_search_and_conflicts(client, auth, project):
    pid = project['id']
    result = client.get('/api/v1/projects?artist=test%20artist&bpm=92', headers=auth).json()
    assert result['total'] == 1 and result['items'][0]['id'] == pid
    assert client.get('/api/v1/projects?bpm_min=100').json()['total'] == 0
    assert client.get('/api/v1/projects?q=morning').json()['total'] == 1
    updated = dict(title='Blue Morning 2', artist='Test Artist', bpm=95)
    response = client.patch(f'/api/v1/projects/{pid}/metadata', json={'expected_revision':1,'metadata':updated}, headers=auth)
    assert response.status_code == 200 and response.json()['revision'] == 2
    stale = client.patch(f'/api/v1/projects/{pid}/metadata', json={'expected_revision':1,'metadata':updated}, headers=auth)
    assert stale.status_code == 409
    assert client.get(f'/api/v1/projects/{pid}/revisions').json()['items'][0]['number'] == 2
    restored = client.post(f'/api/v1/projects/{pid}/revisions/1/restore', json={'expected_revision':2}, headers=auth)
    assert restored.status_code == 200
    assert restored.json()['title'] == 'Blue Morning' and restored.json()['revision'] == 3
    deleted = client.request('DELETE', f'/api/v1/projects/{pid}', json={'expected_revision':3}, headers=auth)
    assert deleted.status_code == 200
    assert client.get(f'/api/v1/projects/{pid}').status_code == 404
    assert client.get('/api/v1/projects?trash=true').json()['total'] == 1
    assert client.post(f'/api/v1/projects/{pid}/restore',headers=auth).status_code == 200
    assert client.get(f'/api/v1/projects/{pid}').status_code == 200


def test_manifest_validation_and_history(client, auth, project):
    pid = project['id']
    bad = client.put(f'/api/v1/projects/{pid}/document', json={'expected_revision':1,'manifest':{'tracks':[]}}, headers=auth)
    assert bad.status_code == 422
    manifest={'schema_version':'1.0','settings':{'bpm':92},'tracks':[{'id':'piano','type':'midi','clips':[]}]}
    good = client.put(f'/api/v1/projects/{pid}/document', json={'expected_revision':1,'manifest':manifest}, headers=auth)
    assert good.status_code == 200
    assert good.json()['manifest']['tracks'][0]['id']=='piano'
    previous = client.get(f'/api/v1/projects/{pid}/revisions/1').json()
    assert previous['snapshot']['manifest']['tracks']==[]


def test_upload_download_remove_restore(client, auth, project):
    pid=project['id']
    midi=b'MThd'+struct.pack('>IHHH',6,0,1,480)+b'MTrk'+struct.pack('>I',4)+b'\0\xff\x2f\0'
    upload=client.post(f'/api/v1/projects/{pid}/assets',data={'kind':'midi','expected_revision':'1'},files={'file':('example.mid',io.BytesIO(midi),'audio/midi')},headers=auth)
    assert upload.status_code==201,upload.text
    obj=upload.json()['assets'][0]
    assert obj['sha256'] and obj['kind']=='midi'
    content=client.get(f'/api/v1/projects/{pid}/assets/{obj["id"]}/content')
    assert content.content==midi
    assert client.get('/api/v1/projects?has_midi=true').json()['total']==1
    removed=client.request('DELETE',f'/api/v1/projects/{pid}/assets/{obj["id"]}',json={'expected_revision':2},headers=auth)
    assert removed.status_code==200 and removed.json()['revision']==3
    assert client.get('/api/v1/projects?has_midi=true').json()['total']==0
    restored=client.post(f'/api/v1/projects/{pid}/revisions/2/restore',json={'expected_revision':3},headers=auth)
    assert restored.json()['assets'][0]['id']==obj['id']
    assert client.get('/api/v1/projects?has_midi=true').json()['total']==1


def test_bad_file_and_cross_project(client, auth, project):
    pid=project['id']
    bad=client.post(f'/api/v1/projects/{pid}/assets',data={'kind':'wav','expected_revision':'1'},files={'file':('not.wav',io.BytesIO(b'bad'),'audio/wav')},headers=auth)
    assert bad.status_code==415
    missing=client.get('/api/v1/projects/unknown/assets/unknown/content')
    assert missing.status_code==404
    assert client.get('/api/v1/projects?limit=101').status_code==422


def test_static_pages(client):
    assert client.get('/').status_code == 200
    assert 'Project Hub' in client.get('/').text
    assert client.get('/static/app.js').status_code == 200
