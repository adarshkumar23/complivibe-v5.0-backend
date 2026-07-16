from tests.helpers.auth_org import bootstrap_org_user, login_user, org_headers
from app.core.security import get_password_hash
from app.models.user import User
from app.models.membership import Membership
from app.models.role import Role
import uuid

def _user(db, org_id, email, role):
    u=User(email=email, full_name=email, hashed_password=get_password_hash("Pass1234!@"), status="active", is_active=True, is_superuser=False)
    db.add(u); db.flush()
    r=db.query(Role).filter(Role.organization_id==uuid.UUID(org_id), Role.name==role).one()
    db.add(Membership(organization_id=uuid.UUID(org_id), user_id=u.id, role_id=r.id, status="active")); db.commit()
    return u

def test_permissions_endpoint_reflects_role_and_no_leak(client, db_session):
    org=bootstrap_org_user(client, email_prefix="perm-ep")
    org_id=org["organization_id"]
    rev=_user(db_session, org_id, "perm-ep-rev@example.com", "reviewer")
    cm=_user(db_session, org_id, "perm-ep-cm@example.com", "compliance_manager")

    rh=org_headers(login_user(client, rev.email), org_id)
    ch=org_headers(login_user(client, cm.email), org_id)

    rr=client.get("/api/v1/auth/permissions", headers=rh); assert rr.status_code==200
    cr=client.get("/api/v1/auth/permissions", headers=ch); assert cr.status_code==200
    rcodes=set(rr.json()["permission_codes"]); ccodes=set(cr.json()["permission_codes"])

    # response shape: exactly two keys, nothing sensitive
    assert set(rr.json().keys())=={"organization_id","permission_codes"}, rr.json().keys()

    # reviewer reflects the de-scope: no risks:write / evidence:write / compliance_policies:approve
    for revoked in ("risks:write","evidence:write","compliance_policies:approve"):
        assert revoked not in rcodes, f"reviewer should NOT have {revoked}"
    # reviewer keeps reads + quorum approves
    assert "risks:read" in rcodes and "governance_override:approve" in rcodes
    # compliance_manager still has risks:write
    assert "risks:write" in ccodes
    print("reviewer codes:", len(rcodes), "| manager codes:", len(ccodes))
