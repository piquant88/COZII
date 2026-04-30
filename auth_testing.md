# Emergent Auth Testing Playbook

## Step 1: Create Test User & Session via mongosh
```
mongosh --eval "
use('test_database');
var userId = 'test-user-' + Date.now();
var sessionToken = 'test_session_' + Date.now();
db.users.insertOne({
  user_id: userId,
  email: 'test.user.' + Date.now() + '@example.com',
  name: 'Test User',
  picture: 'https://via.placeholder.com/150',
  created_at: new Date()
});
db.user_sessions.insertOne({
  user_id: userId,
  session_token: sessionToken,
  expires_at: new Date(Date.now() + 7*24*60*60*1000),
  created_at: new Date()
});
print('Session token: ' + sessionToken);
print('User ID: ' + userId);
"
```

## Step 2: Test Backend API
```
curl -X GET "https://YOUR-DOMAIN/api/auth/me" \
  -H "Authorization: Bearer YOUR_SESSION_TOKEN"
```

## Step 3: Browser Testing (Playwright)
```
await page.context.add_cookies([{
    "name": "session_token",
    "value": "YOUR_SESSION_TOKEN",
    "domain": "YOUR_DOMAIN",
    "path": "/",
    "httpOnly": True,
    "secure": True,
    "sameSite": "None"
}])
await page.goto("https://YOUR_DOMAIN")
```

## Checklist
- [ ] user_id is custom UUID (not MongoDB `_id`)
- [ ] Session `user_id` matches user's `user_id` exactly
- [ ] All Mongo queries use `{"_id": 0}` projection
- [ ] `/api/auth/me` returns user data
- [ ] Dashboard loads without redirect to login
