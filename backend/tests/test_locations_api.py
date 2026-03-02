import uuid

from sqlalchemy import text


def _login(client, email: str, password: str) -> tuple[str, str]:
    response = client.post('/api/v1/auth/login', json={'email': email, 'password': password})
    assert response.status_code == 200
    payload = response.json()['data']
    return payload['access_token'], payload['user']['organization_id']


def _create_subaccount(client, token: str, org_id: str, name: str) -> str:
    response = client.post(
        f'/api/v1/organizations/{org_id}/subaccounts',
        json={'name': name},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == 200
    return response.json()['data']['subaccount']['id']


def _create_business_location(client, token: str, org_id: str, name: str) -> str:
    response = client.post(
        f'/api/v1/organizations/{org_id}/business-locations',
        json={'name': name},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == 200
    return response.json()['data']['business_location']['id']


def test_create_location_without_business_location_succeeds(client, db_session) -> None:
    token, org_id = _login(client, 'org-admin@example.com', 'pass-org-admin')
    subaccount_id = _create_subaccount(client, token, org_id, 'Ops Alpha')

    response = client.post(
        f'/api/v1/organizations/{org_id}/locations',
        json={'name': 'Austin HQ'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == 200
    payload = response.json()['data']['location']
    assert payload['organization_id'] == org_id
    assert payload['name'] == 'Austin HQ'
    assert payload['business_location_id'] is None

    row = db_session.execute(
        text(
            '''
            SELECT organization_id, sub_account_id, name, business_location_id
            FROM locations
            WHERE id = :location_id
            '''
        ),
        {'location_id': payload['id']},
    ).mappings().one()
    assert row['organization_id'] == org_id
    assert row['sub_account_id'] == subaccount_id
    assert row['name'] == 'Austin HQ'
    assert row['business_location_id'] is None


def test_create_location_with_same_org_business_location_succeeds(client, db_session) -> None:
    token, org_id = _login(client, 'org-admin@example.com', 'pass-org-admin')
    _create_subaccount(client, token, org_id, 'Ops Beta')
    business_location_id = _create_business_location(client, token, org_id, 'Main Street')

    response = client.post(
        f'/api/v1/organizations/{org_id}/locations',
        json={'name': 'Dallas Branch', 'business_location_id': business_location_id},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == 200
    payload = response.json()['data']['location']
    assert payload['business_location_id'] == business_location_id

    stored_business_location_id = db_session.execute(
        text('SELECT business_location_id FROM locations WHERE id = :location_id'),
        {'location_id': payload['id']},
    ).scalar_one()
    assert stored_business_location_id == business_location_id


def test_create_location_with_cross_org_business_location_returns_403(client, db_session) -> None:
    token_a, org_a = _login(client, 'org-admin@example.com', 'pass-org-admin')
    token_b, org_b = _login(client, 'b@example.com', 'pass-b')
    _create_subaccount(client, token_a, org_a, 'Ops Gamma')
    business_location_id = _create_business_location(client, token_b, org_b, 'Remote Office')

    response = client.post(
        f'/api/v1/organizations/{org_a}/locations',
        json={'name': 'Illegal Link', 'business_location_id': business_location_id},
        headers={'Authorization': f'Bearer {token_a}'},
    )

    assert response.status_code == 403
    details = response.json()['errors'][0]['details']
    assert details['reason_code'] == 'business_location_org_mismatch'

    location_count = db_session.execute(
        text(
            '''
            SELECT count(*)
            FROM locations
            WHERE organization_id = :organization_id
              AND name = :name
            '''
        ),
        {'organization_id': org_a, 'name': 'Illegal Link'},
    ).scalar_one()
    assert location_count == 0


def test_create_location_with_missing_business_location_returns_404(client, db_session) -> None:
    token, org_id = _login(client, 'org-admin@example.com', 'pass-org-admin')
    _create_subaccount(client, token, org_id, 'Ops Delta')
    missing_business_location_id = str(uuid.uuid4())

    response = client.post(
        f'/api/v1/organizations/{org_id}/locations',
        json={'name': 'Unknown Link', 'business_location_id': missing_business_location_id},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == 404
    details = response.json()['errors'][0]['details']
    assert details['reason_code'] == 'business_location_not_found'

    location_count = db_session.execute(
        text(
            '''
            SELECT count(*)
            FROM locations
            WHERE organization_id = :organization_id
              AND name = :name
            '''
        ),
        {'organization_id': org_id, 'name': 'Unknown Link'},
    ).scalar_one()
    assert location_count == 0