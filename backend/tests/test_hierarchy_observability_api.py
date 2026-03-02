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


def _create_location(client, token: str, org_id: str, name: str, business_location_id: str | None = None) -> str:
    payload = {'name': name}
    if business_location_id is not None:
        payload['business_location_id'] = business_location_id
    response = client.post(
        f'/api/v1/organizations/{org_id}/locations',
        json=payload,
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == 200
    return response.json()['data']['location']['id']


def test_hierarchy_health_reports_zero_location_org(client) -> None:
    token, org_id = _login(client, 'org-admin@example.com', 'pass-org-admin')

    response = client.get(
        f'/api/v1/organizations/{org_id}/hierarchy/health',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == 200
    payload = response.json()['data']['hierarchy_health']
    assert payload == {
        'total_locations': 0,
        'linked_locations': 0,
        'unlinked_locations': 0,
        'linkage_percentage': 0.0,
    }


def test_hierarchy_health_reports_mixed_linkage(client, db_session) -> None:
    token, org_id = _login(client, 'org-admin@example.com', 'pass-org-admin')
    _create_subaccount(client, token, org_id, 'Ops Alpha')
    business_location_id = _create_business_location(client, token, org_id, 'Main Street')
    _create_location(client, token, org_id, 'Austin HQ')
    linked_location_id = _create_location(client, token, org_id, 'Dallas Branch', business_location_id)

    response = client.get(
        f'/api/v1/organizations/{org_id}/hierarchy/health',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == 200
    payload = response.json()['data']['hierarchy_health']
    assert payload['total_locations'] == 2
    assert payload['linked_locations'] == 1
    assert payload['unlinked_locations'] == 1
    assert payload['linkage_percentage'] == 50.0

    stored_linked_count = db_session.execute(
        text(
            '''
            SELECT count(*)
            FROM locations
            WHERE organization_id = :organization_id
              AND business_location_id IS NOT NULL
            '''
        ),
        {'organization_id': org_id},
    ).scalar_one()
    assert stored_linked_count == 1

    stored_business_location_id = db_session.execute(
        text('SELECT business_location_id FROM locations WHERE id = :location_id'),
        {'location_id': linked_location_id},
    ).scalar_one()
    assert stored_business_location_id == business_location_id


def test_hierarchy_health_blocks_cross_org_access(client) -> None:
    token_a, _org_a = _login(client, 'org-admin@example.com', 'pass-org-admin')
    _token_b, org_b = _login(client, 'b@example.com', 'pass-b')

    response = client.get(
        f'/api/v1/organizations/{org_b}/hierarchy/health',
        headers={'Authorization': f'Bearer {token_a}'},
    )

    assert response.status_code == 403
    details = response.json()['errors'][0]['details']
    assert details['reason_code'] == 'organization_scope_mismatch'


def test_hierarchy_health_response_shape_is_deterministic(client, db_session) -> None:
    token, org_id = _login(client, 'org-admin@example.com', 'pass-org-admin')
    _create_subaccount(client, token, org_id, 'Ops Beta')
    _create_location(client, token, org_id, 'Seattle Hub')

    response = client.get(
        f'/api/v1/organizations/{org_id}/hierarchy/health',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == 200
    assert list(response.json()['data'].keys()) == ['hierarchy_health']
    assert list(response.json()['data']['hierarchy_health'].keys()) == [
        'total_locations',
        'linked_locations',
        'unlinked_locations',
        'linkage_percentage',
    ]
