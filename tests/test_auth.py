def test_login_page_renders(client):
    """Test that the login page loads successfully."""
    response = client.get('/auth/login')
    assert response.status_code == 200
    assert b'Phoenix Terminal' in response.data

def test_successful_login(client, admin_user):
    """Test logging in with valid credentials."""
    response = client.post('/auth/login', data={
        'username': 'testadmin',
        'password': 'Admin123'
    }, follow_redirects=True)
    
    assert response.status_code == 200
    assert b'Terminal Operational' in response.data or b'Dashboard' in response.data

def test_failed_login(client, admin_user):
    """Test logging in with invalid credentials."""
    response = client.post('/auth/login', data={
        'username': 'testadmin',
        'password': 'WrongPassword'
    }, follow_redirects=True)
    
    assert response.status_code == 200
    assert b'Invalid username or password' in response.data

def test_logout(client, admin_user):
    """Test that logging out clears the session."""
    client.post('/auth/login', data={
        'username': 'testadmin',
        'password': 'Admin123'
    }, follow_redirects=True)
    
    response = client.get('/auth/logout', follow_redirects=True)
    assert response.status_code == 200
    assert b'You have been logged out' in response.data
    
    # Verify we can't access a protected route anymore
    dash_response = client.get('/billing/')
    assert dash_response.status_code == 302 # Redirect to login
