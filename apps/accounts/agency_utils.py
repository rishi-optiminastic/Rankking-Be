"""Agency team role resolution.

Identity is email-based across this codebase, so an agency is identified by its
owner's email (an ``AccountProfile`` with ``account_type=agency``). The owner is
the implicit Admin; invited teammates are ``AgencyMembership`` rows. Roles are
always re-derived here from server records — never trusted from the request.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.organizations.models import Organization

from .models import AgencyMembership
from .subscription_utils import get_account_type

# 1 Admin (the owner) + this many invited teammates.
MAX_AGENCY_MEMBERS = 2


@dataclass(frozen=True)
class AgencyContext:
    """The caller's place in an agency: which agency, and what role."""

    agency_email: str
    role: str  # "admin" | "member"

    @property
    def is_admin(self) -> bool:
        return self.role == AgencyMembership.Role.ADMIN


def _memberships(normalized: str) -> list[AgencyContext]:
    """Active membership rows for ``normalized``, as contexts."""
    rows = AgencyMembership.objects.filter(
        member_email=normalized, status=AgencyMembership.Status.ACTIVE
    ).only("agency_email", "role")
    return [AgencyContext(agency_email=r.agency_email, role=r.role) for r in rows]


def get_agency_contexts(email: str | None) -> list[AgencyContext]:
    """EVERY agency ``email`` belongs to: their own, plus each active membership.

    Owning an agency and being invited to someone else's are not mutually
    exclusive, and treating them as such is what broke team access: an invited
    teammate whose own ``account_type`` was already ``agency`` short-circuited on
    their own agency below, so the membership row was written, listed in the
    roster as "active", and then read by nothing. They never saw a single brand
    of the agency that invited them.

    Own agency first, so ``get_agency_context`` keeps returning the identity a
    user acts under by default.
    """
    normalized = (email or "").strip().lower()
    if not normalized:
        return []

    contexts: list[AgencyContext] = []
    if get_account_type(normalized) == "agency":
        contexts.append(AgencyContext(agency_email=normalized, role=AgencyMembership.Role.ADMIN))

    seen = {c.agency_email for c in contexts}
    for ctx in _memberships(normalized):
        if ctx.agency_email not in seen:
            contexts.append(ctx)
            seen.add(ctx.agency_email)
    return contexts


def get_agency_context(email: str | None) -> AgencyContext | None:
    """The caller's PRIMARY agency identity, or ``None`` if they are on none.

    Own agency wins, so an agency owner who is also someone's teammate still
    administers their own team rather than being demoted into another. Callers
    deciding what a user may *see* want ``get_agency_contexts`` instead: this
    one answers "who is this user", not "what can they reach".
    """
    contexts = get_agency_contexts(email)
    return contexts[0] if contexts else None


def is_agency_admin(email: str | None) -> bool:
    ctx = get_agency_context(email)
    return bool(ctx and ctx.is_admin)


def agency_role_for(email: str | None, agency_email: str) -> str | None:
    """``email``'s role within one specific agency, or ``None`` if not on it.

    Write checks need this rather than ``get_agency_context().role``: a user who
    owns an agency is Admin *there*, and that must not read across as Admin on a
    different agency's brands they were merely invited to.
    """
    target = (agency_email or "").strip().lower()
    for ctx in get_agency_contexts(email):
        if ctx.agency_email == target:
            return ctx.role
    return None


def readable_owner_emails(email: str | None) -> list[str]:
    """Every ``owner_email`` whose brands ``email`` may READ: their own + each agency.

    A union, not a substitution. Callers used to REPLACE the caller's email with
    their agency's, which dropped any brand the caller owned personally the moment
    they joined a team, and, paired with the single-context bug, showed an
    invited teammate only their own brands and never the agency's.
    """
    normalized = (email or "").strip().lower()
    if not normalized:
        return []
    emails = [normalized]
    for ctx in get_agency_contexts(normalized):
        if ctx.agency_email not in emails:
            emails.append(ctx.agency_email)
    return emails


def writable_owner_emails(email: str | None) -> list[str]:
    """As above, but only agencies ``email`` ADMINISTERS (plus always their own)."""
    normalized = (email or "").strip().lower()
    if not normalized:
        return []
    emails = [normalized]
    for ctx in get_agency_contexts(normalized):
        if ctx.is_admin and ctx.agency_email not in emails:
            emails.append(ctx.agency_email)
    return emails


def agency_org_ids(agency_email: str) -> list[int]:
    """The brand/project ids owned by the agency (all brands its team works on)."""
    return list(
        Organization.objects.filter(owner_email=(agency_email or "").strip().lower()).values_list(
            "id", flat=True
        )
    )
