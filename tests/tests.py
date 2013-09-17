import re
import urllib
import urllib2
import httplib
import json
import shutil
import os
import pytest

port = "8889"
server = "http://localhost:"+port



@pytest.fixture
def givenTestStorage():
    copy_and_overwrite("../storage-example","../tmp/test-storage")


def test_get_webfinger():
	request = urllib2.urlopen(server+"/.well-known/host-meta.json?resource=acct%3Ausername%40domain.net");
	response = request.read();
	print response
	print request.info()
	resultJSON = json.loads(response)
	link = resultJSON['links'][0]
	assert link["href"] == server + "/storage/username"
	assert link["rel"] == "remoteStorage"
	assert link["type"] == "https://www.w3.org/community/rww/wiki/read-write-web-00#simple"
	props = link["properties"]
	assert props["auth-method"] == "https://tools.ietf.org/html/draft-ietf-oauth-v2-26#section-4.2"
	assert props["auth-endpoint"] == server + "/auth/username"
	assert request.info()['Content-Type'].startswith('application/json')
	

def test_auth_page():
	request = urllib2.urlopen(server+"/auth/marco"+"?redirect_uri=https%3A%2F%2Fmyfavoritedrinks.5apps.com%2F&client_id=myfavoritedrinks.5apps.com&scope=myfavoritedrinks%3Arw&response_type=token");
	response = request.read();
	assert "<h1>Allow Remote Storage Access?</h1>" in response
	assert "marco" in response
	assert "myfavoritedrinks" in response
	assert "Full Access" in response
	assert "myfavoritedrinks.5apps.com" in response

def test_confirm_permission_with_password_and_redirect_to_app():
	values = {'password' : 'password'}
	data = urllib.urlencode(values)
	headers = {"Content-type": "application/x-www-form-urlencoded",
            "Accept": "text/plain"}	
	conn = httplib.HTTPConnection('localhost:'+port)
	conn.request("POST", "/auth/user1"+"?redirect_uri=https%3A%2F%2Fmyfavoritedrinks.5apps.com%2F&client_id=myfavoritedrinks.5apps.com&scope=myfavoritedrinks%3Arw&response_type=token",data,headers)
	r = conn.getresponse()
	print r.status, r.reason
	redirectUrl = r.getheader('Location')
	expectedRedirectUrlPrefix = 'https://myfavoritedrinks.5apps.com/#access_token='
	assert redirectUrl.startswith(expectedRedirectUrlPrefix)
	assert len(redirectUrl[len(expectedRedirectUrlPrefix):])>=10

def test_storage_cors():
	conn = httplib.HTTPConnection('localhost:'+port)
	conn.request("OPTIONS", "/storage/user1/myfavoritedrinks/")
	r = conn.getresponse()
	assert r.status == 200;
	assert r.getheader('Access-Control-Allow-Origin') == "*"

def test_storage_cors():
	r = makeRequest("/storage/user1/myfavoritedrinks/",'OPTIONS')
	assert r.status == 200;
	assert r.getheader('Access-Control-Allow-Origin') == "*"

def test_storage_directory_listing_needs_bearer_token(givenTestStorage):	
	r = makeRequest("/storage/user1/myfavoritedrinks/")
	assert r.status == 401;

def test_storage_directory_listing_needs_valid_bearer_token(givenTestStorage):
	r = makeRequest("/storage/user1/myfavoritedrinks/",'GET',"invalid-bearer-token")
	assert r.status == 401;
	
def test_storage_directory_listing_needs_bearer_token_matching_user(givenTestStorage):
	bearerToken = requestBearerToken()
	r = makeRequest("/storage/otheruser/myfavoritedrinks/",'GET',bearerToken)
	assert r.status == 401;	

def test_storage_directory_listing(givenTestStorage):
	bearerToken = requestBearerToken()
	r = makeRequest("/storage/user1/module/",'GET',bearerToken)	
	assert r.status == 200;
	assert r.getheader('Content-Type') == 'application/json';
	dirList = json.loads(r.read())
	assert dirList['file.txt']
	assert dirList['dir/']

def test_storage_directory_listing_for_non_existing_dir(givenTestStorage):
	bearerToken = requestBearerToken()
	r = makeRequest("/storage/user1/notextisting/",'GET',bearerToken)	
	assert r.status == 404;
	dirList = json.loads(r.read())
	assert len(dirList) == 0
	
def test_storage_read_data(givenTestStorage):
	bearerToken = requestBearerToken()
	r = makeRequest("/storage/user1/module/file.txt",'GET',bearerToken)	
	assert r.status == 200
	fileContent = r.read()
	assert fileContent == "text"
	
def test_storage_save_data(givenTestStorage):
	bearerToken = requestBearerToken()
	r = makeRequest("/storage/user1/module/new-file.txt",'PUT',bearerToken,"new text")	
	assert r.status == 200
	r = makeRequest("/storage/user1/module/new-file.txt",'GET',bearerToken)	
	fileContent = r.read()
	assert fileContent == "new text"

def test_storage_save_data_in_new_path(givenTestStorage):
	bearerToken = requestBearerToken()
	r = makeRequest("/storage/user1/module/newdir/new-file.txt",'PUT',bearerToken,"new text","text/plain")	
	assert r.status == 200
	r = makeRequest("/storage/user1/module/newdir/new-file.txt",'GET',bearerToken)	
	fileContent = r.read()
	assert fileContent == "new text"	
	assert r.getheader('Content-Type') == "text/plain"
	r = makeRequest("/storage/user1/module/newdir/",'GET',bearerToken)
	dirList = json.loads(r.read())
	assert len(dirList) == 1
	assert dirList['new-file.txt']
		

def test_storage_get_returns_correct_content_type(givenTestStorage):
	bearerToken = requestBearerToken()
	r = makeRequest("/storage/user1/module/newdir/json",'PUT',bearerToken,'{"key":"value"}',"application/json")	
	assert r.status == 200
	r = makeRequest("/storage/user1/module/newdir/json",'GET',bearerToken)	
	fileContent = r.read()
	assert r.getheader('Content-Type') == "application/json"
	

def test_storage_save_updates_modified_date_of_ancestor_folders(givenTestStorage):
	bearerToken = requestBearerToken()
	r = makeRequest("/storage/user1/",'GET',bearerToken)	
	dirList1 = json.loads(r.read())	
	moduleDirVersion1 = dirList1['module/']
	r = makeRequest("/storage/user1/module/dir/new-file.txt",'PUT',bearerToken,"new text")	
	assert r.status == 200			
	r = makeRequest("/storage/user1/",'GET',bearerToken)	
	dirList2 = json.loads(r.read())
	assert dirList2['module/'] != moduleDirVersion1

def test_storage_delete_file(givenTestStorage):
	bearerToken = requestBearerToken()
	r = makeRequest("/storage/user1/module/dir/new-file.txt",'PUT',bearerToken,"new text")	
	assert r.status == 200			
	r = makeRequest("/storage/user1/module/dir/new-file.txt",'DELETE',bearerToken)
	assert r.status == 200			
	r = makeRequest("/storage/user1/module/dir/",'GET',bearerToken)	
	dirList = json.loads(r.read())
	assert not 'new-file.txt' in dirList
	assert len(dirList) == 0
	r = makeRequest("/storage/user1/module/",'GET',bearerToken)	
	dirList = json.loads(r.read())
	assert not 'dir/' in dirList

# utils
def requestBearerToken():
	values = {'password' : 'password'}
	data = urllib.urlencode(values)
	headers = {"Content-type": "application/x-www-form-urlencoded"}	
	conn = httplib.HTTPConnection('localhost:'+port)
	conn.request("POST", "/auth/user1"+"?redirect_uri=https%3A%2F%2Fmyfavoritedrinks.5apps.com%2F&client_id=myfavoritedrinks.5apps.com&scope=myfavoritedrinks%3Arw&response_type=token",data,headers)
	r = conn.getresponse()		
	redirectUrl = r.getheader('Location')
	expectedRedirectUrlPrefix = 'https://myfavoritedrinks.5apps.com/#access_token='
	return redirectUrl[len(expectedRedirectUrlPrefix):]


def makeRequest(path,method="GET",bearerToken=None,data="",contentType=None):
	conn = httplib.HTTPConnection('localhost:'+port)
	headers = {}
	if bearerToken:
		headers['Authorization'] = "Bearer "+bearerToken
	if contentType:
		headers['Content-Type'] = contentType
	conn.request(method, path,data,headers)
	return conn.getresponse()
	
def copy_and_overwrite(from_path, to_path):
    if os.path.exists(to_path):
        shutil.rmtree(to_path)
    shutil.copytree(from_path, to_path)
