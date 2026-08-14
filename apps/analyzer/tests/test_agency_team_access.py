"""An invited teammate must actually reach the brands they were invited to.

Reproduces a bug verified against production. ``devops@optiminastic.com`` (an
agency) invited ``tech1@optiminastic.com``; the roster listed tech1 as role
``member``, status ``active``. But:

    GET /api/agency/role/?email=tech1@…      -> {"agency_email": "tech1@…", "role": "admin"}
    GET /api/organizations/?email=tech1@…    -> only tech1's OWN org, never the agency's

``get_agency_context`` returned on ``account_type == "agency"`` before it ever
looked at membership rows, so any invitee who already held an agency account
short-circuited on their own agency. The invite wrote a row that nothing read.

The second class of test pins the Member/Admin split the roster legend promises:
"View reports and work through assigned actions" is read plus assigned work, not
brand-wide write.
"""

from django.test import TestCase

from apps.accounts.agency_utils import agency_role_for, get_agency_context, get_agency_contexts
from apps.accounts.models import AccountProfile, AgencyMembership
from apps.analyzer.access import accessible_org_ids, writable_org_ids
from apps.organizations.models import Organization

AGENCY = "devops@optiminastic.com"
TEAMMATE = "tech1@optiminastic.com"


class AgencyTeamAccessTests(TestCase):
    def setUp(self):
        AccountProfile.objects.create(email=AGENCY, account_type="agency")
        self.agency_org = Organization.objects.create(
            name="Signalor", owner_email=AGENCY, url="https://signalor.ai"
        )
        AgencyMembership.objects.create(
            agency_email=AGENCY,
            member_email=TEAMMATE,
            role=AgencyMembership.Role.MEMBER,
            status=AgencyMembership.Status.ACTIVE,
        )

    def _make_teammate_own_an_agency(self):
        """The exact production shape: the invitee also holds an agency account."""
        AccountProfile.objects.create(email=TEAMMATE, account_type="agency")
        return Organization.objects.create(
            name="Teammate's own brand", owner_email=TEAMMATE, url="https://own.example"
        )

    def test_plain_teammate_reaches_the_agency_brand(self):
        self.assertIn(self.agency_org.pk, accessible_org_ids(TEAMMATE))

    def test_teammate_who_owns_an_agency_still_reaches_the_inviting_agency(self):
        self._make_teammate_own_an_agency()
        self.assertIn(self.agency_org.pk, accessible_org_ids(TEAMMATE))

    def test_owning_an_agency_is_not_given_up_by_joining_another(self):
        own_org = self._make_teammate_own_an_agency()
        emails = {c.agency_email for c in get_agency_contexts(TEAMMATE)}
        self.assertEqual(emails, {TEAMMATE, AGENCY})
        # Their own identity is unchanged: still Admin of their own agency.
        self.assertEqual(get_agency_context(TEAMMATE).agency_email, TEAMMATE)
        self.assertIn(own_org.pk, writable_org_ids(TEAMMATE))

    def test_role_is_resolved_per_agency_not_globally(self):
        self._make_teammate_own_an_agency()
        self.assertEqual(agency_role_for(TEAMMATE, TEAMMATE), AgencyMembership.Role.ADMIN)
        self.assertEqual(agency_role_for(TEAMMATE, AGENCY), AgencyMembership.Role.MEMBER)

    def test_a_member_may_read_the_agency_brand_but_not_write_it(self):
        self.assertIn(self.agency_org.pk, accessible_org_ids(TEAMMATE))
        self.assertNotIn(self.agency_org.pk, writable_org_ids(TEAMMATE))

    def test_an_admin_teammate_may_write_the_agency_brand(self):
        AgencyMembership.objects.filter(member_email=TEAMMATE).update(
            role=AgencyMembership.Role.ADMIN
        )
        self.assertIn(self.agency_org.pk, writable_org_ids(TEAMMATE))

    def test_an_invited_but_not_yet_active_teammate_reaches_nothing(self):
        AgencyMembership.objects.filter(member_email=TEAMMATE).update(
            status=AgencyMembership.Status.INVITED
        )
        self.assertNotIn(self.agency_org.pk, accessible_org_ids(TEAMMATE))

    def test_a_stranger_reaches_nothing(self):
        self.assertEqual(accessible_org_ids("nobody@evil.com"), set())
        self.assertEqual(get_agency_contexts("nobody@evil.com"), [])


class OrganizationListScopingTests(TestCase):
    """The endpoint the dashboard actually calls to populate the brand switcher.

    It resolved a single agency context and SUBSTITUTED that email for the
    caller's, so it needed fixing separately: the union in ``accessible_org_ids``
    alone would never have reached the brand list a teammate sees on login.
    """

    def setUp(self):
        AccountProfile.objects.create(email=AGENCY, account_type="agency")
        self.agency_org = Organization.objects.create(
            name="Signalor", owner_email=AGENCY, url="https://signalor.ai"
        )
        AgencyMembership.objects.create(
            agency_email=AGENCY,
            member_email=TEAMMATE,
            role=AgencyMembership.Role.MEMBER,
            status=AgencyMembership.Status.ACTIVE,
        )

    def _slugs_for(self, email: str) -> set[str]:
        resp = self.client.get("/api/organizations/", {"email": email})
        self.assertEqual(resp.status_code, 200)
        return {row["slug"] for row in resp.json()}

    def test_teammate_who_owns_an_agency_sees_both_brands(self):
        AccountProfile.objects.create(email=TEAMMATE, account_type="agency")
        own = Organization.objects.create(
            name="Own", owner_email=TEAMMATE, url="https://own.example"
        )
        self.assertEqual(self._slugs_for(TEAMMATE), {self.agency_org.slug, own.slug})

    def test_a_plain_teammates_own_brand_is_not_hidden_by_joining(self):
        own = Organization.objects.create(
            name="Own", owner_email=TEAMMATE, url="https://own.example"
        )
        self.assertEqual(self._slugs_for(TEAMMATE), {self.agency_org.slug, own.slug})

    def test_a_stranger_sees_none_of_the_agencys_brands(self):
        self.assertEqual(self._slugs_for("nobody@evil.com"), set())
