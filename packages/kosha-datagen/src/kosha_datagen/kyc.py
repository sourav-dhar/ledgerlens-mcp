"""KYC profiles, their documents and status history, and sanctions and PEP screening.

PAN and Aadhaar never appear in full: a PAN is drawn only to derive its last four
characters, and the stored values are a KMS-style token and an Aadhaar vault reference.
"""

import random
from datetime import date, datetime, timedelta
from decimal import Decimal

from kosha_datagen import refs
from kosha_datagen.chance import pick
from kosha_datagen.config import GenerationConfig
from kosha_datagen.parties import Fate, Profile
from kosha_datagen.rows import KycDocument, KycEvent, KycProfile, ScreeningResult
from kosha_domain.ids import IdPrefix, new_id
from kosha_domain.lifecycles import KycStatus
from kosha_domain.vocabulary import (
    Actor,
    KycDocumentStatus,
    KycDocumentType,
    KycType,
    ListSource,
    OvdType,
    PanStatus,
    Persona,
    RiskCategory,
    ScreeningDecision,
)

K = KycStatus
RE_KYC_YEARS = {RiskCategory.HIGH: 2, RiskCategory.MEDIUM: 8, RiskCategory.LOW: 10}
"""Periodic updation intervals, RBI KYC Master Direction §38."""
OVERDUE_AFTER = timedelta(days=90)
_ONBOARDING = {
    KycType.V_CIP: (K.NOT_STARTED, K.PENDING_DOCUMENTS, K.PENDING_VCIP, K.IN_REVIEW, K.VERIFIED),
    KycType.FULL_KYC: (K.NOT_STARTED, K.PENDING_DOCUMENTS, K.IN_REVIEW, K.VERIFIED),
    KycType.CKYC_DOWNLOAD: (K.NOT_STARTED, K.PENDING_DOCUMENTS, K.IN_REVIEW, K.VERIFIED),
    KycType.MIN_KYC: (K.NOT_STARTED, K.PENDING_DOCUMENTS, K.IN_REVIEW, K.VERIFIED),
}
_PROSPECT_ENDS = {
    K.NOT_STARTED: 2,
    K.PENDING_DOCUMENTS: 4,
    K.PENDING_VCIP: 4,
    K.IN_REVIEW: 3,
    K.ON_HOLD: 1,
    K.ESCALATED: 1,
    K.REJECTED: 1,
}
_PAN_STATUSES = {PanStatus.VALID: 970, PanStatus.NOT_AADHAAR_LINKED: 25, PanStatus.INVALID: 5}
_HIT_LISTS = {ListSource.UN_SC: 1, ListSource.OFAC_SDN: 2, ListSource.MHA_UAPA: 1}
_RATIONALE = {
    RiskCategory.LOW: "Income and activity consistent with declared profile",
    RiskCategory.MEDIUM: "Cash-intensive occupation or cross-border income",
    RiskCategory.HIGH: "Enhanced due diligence applied",
}


def _kyc_type(profile: Profile, rng: random.Random) -> KycType:
    if profile.persona is Persona.NRI:
        return KycType.FULL_KYC
    if profile.persona in (Persona.STUDENT, Persona.GIG_WORKER) and rng.random() < 0.3:
        return KycType.MIN_KYC
    return pick(rng, {KycType.V_CIP: 55, KycType.FULL_KYC: 25, KycType.CKYC_DOWNLOAD: 20})


def _history(
    config: GenerationConfig, profile: Profile, kyc_type: KycType, rng: random.Random
) -> list[tuple[KycStatus, datetime, Actor]]:
    """Statuses with when and who, ending in the profile's current status."""
    path = list(_ONBOARDING[kyc_type])
    if profile.fate is Fate.PROSPECT:
        end = pick(rng, _PROSPECT_ENDS)
        if end is K.PENDING_VCIP:
            path = list(_ONBOARDING[KycType.V_CIP])
        detours = {K.ON_HOLD: K.IN_REVIEW, K.ESCALATED: K.IN_REVIEW, K.REJECTED: K.IN_REVIEW}
        path = path[: path.index(detours.get(end, end)) + 1]
        if end in detours:
            path.append(end)
    at = profile.onboarded_at - timedelta(minutes=rng.randint(10, 60))
    steps: list[tuple[KycStatus, datetime, Actor]] = []
    for status in path:
        actor = Actor.STAFF if status in (K.VERIFIED, K.REJECTED, K.ESCALATED) else Actor.CUSTOMER
        if status in (K.NOT_STARTED, K.IN_REVIEW):
            actor = Actor.SYSTEM
        steps.append((status, min(at, config.now), actor))
        at += timedelta(minutes=rng.randint(3, 50))
    return steps


def kyc_rows(
    config: GenerationConfig, profile: Profile, rng: random.Random
) -> tuple[KycProfile, list[KycEvent], list[KycDocument]]:
    kyc_type = _kyc_type(profile, rng)
    steps = _history(config, profile, kyc_type, rng)
    verified_at = next((at for status, at, _ in steps if status is K.VERIFIED), None)
    due: date | None = None
    if verified_at is not None:
        years = RE_KYC_YEARS[profile.risk_category]
        due = date(verified_at.year + years, verified_at.month, min(verified_at.day, 28))
        due_at = datetime.combine(due, datetime.min.time(), verified_at.tzinfo)
        if due < config.as_of:
            steps.append((K.RE_KYC_DUE, due_at, Actor.SYSTEM))
        if due_at + OVERDUE_AFTER < config.now:
            steps.append((K.RE_KYC_OVERDUE, due_at + OVERDUE_AFTER, Actor.SYSTEM))
    kyc_id = new_id(IdPrefix.KYC_PROFILE, at=steps[0][1], rng=rng)
    events = [
        KycEvent(
            event_id=new_id(IdPrefix.KYC_EVENT, at=at, rng=rng),
            kyc_id=kyc_id,
            from_status=steps[i - 1][0] if i else None,
            to_status=status,
            actor=actor,
            reason=_event_reason(status),
            occurred_at=at,
        )
        for i, (status, at, actor) in enumerate(steps)
    ]
    reached_documents = len(steps) > 1
    has_aadhaar = profile.persona is not Persona.NRI and reached_documents
    pan = refs.pan(rng, "P", profile.last_name)
    vcip = kyc_type is KycType.V_CIP and verified_at is not None
    row = KycProfile(
        kyc_id=kyc_id,
        customer_id=profile.customer_id,
        kyc_type=kyc_type,
        kyc_status=steps[-1][0],
        ckyc_number=refs.ckyc_number(rng) if verified_at and rng.random() < 0.7 else None,
        pan_token=f"kms:v1:{refs.hex_token(rng, 40)}" if reached_documents else None,
        pan_last4=pan[-4:] if reached_documents else None,
        pan_status=(pick(rng, _PAN_STATUSES) if reached_documents else None),
        pan_name_match_score=_score(rng, 86, 100) if reached_documents else None,
        aadhaar_ref_token=f"vault:aadhaar:{refs.hex_token(rng, 12)}" if has_aadhaar else None,
        aadhaar_last4=refs.digits(rng, 4) if has_aadhaar else None,
        ovd_type=_ovd(profile, rng) if reached_documents else None,
        vcip_session_id=f"vcip_{refs.hex_token(rng, 20)}" if vcip else None,
        vcip_agent_id=f"vkyc-agent-{rng.randint(1, 40):03d}" if vcip else None,
        liveness_score=_score(rng, 90, 100) if vcip else None,
        face_match_score=_score(rng, 84, 100) if vcip else None,
        vcip_geo_lat=_jitter(rng, profile.city.lat) if vcip else None,
        vcip_geo_lng=_jitter(rng, profile.city.lng) if vcip else None,
        pep_flag=profile.pep,
        sanctions_flag=False,
        fatca_crs_declared=verified_at is not None,
        risk_category=profile.risk_category,
        risk_rationale=("Domestic PEP: " if profile.pep else "")
        + _RATIONALE[profile.risk_category],
        verified_at=verified_at,
        verified_by=(
            f"staff-{rng.randint(100, 160):04d}"
            if verified_at and kyc_type is not KycType.CKYC_DOWNLOAD
            else ("ckyc-registry" if verified_at else None)
        ),
        next_review_due=due,
        created_at=steps[0][1],
    )
    return row, events, _documents(profile, row, rng)


def _event_reason(status: KycStatus) -> str | None:
    return {
        K.PENDING_VCIP: "Documents accepted; video KYC scheduled",
        K.ON_HOLD: "Name mismatch between PAN and Aadhaar",
        K.ESCALATED: "Potential match on screening; referred to compliance",
        K.REJECTED: "Liveness check failed twice",
        K.RE_KYC_DUE: "Periodic updation due",
        K.RE_KYC_OVERDUE: "Periodic updation not completed within 90 days",
    }.get(status)


def _ovd(profile: Profile, rng: random.Random) -> OvdType:
    if profile.persona is Persona.NRI:
        return OvdType.PASSPORT
    weights = {OvdType.AADHAAR: 70, OvdType.VOTER_ID: 12, OvdType.DRIVING_LICENCE: 10}
    return pick(rng, weights | {OvdType.PASSPORT: 8})


def _score(rng: random.Random, low: int, high: int) -> Decimal:
    return Decimal(rng.randint(low * 100, high * 100)) / 100


def _jitter(rng: random.Random, degrees: Decimal) -> Decimal:
    return degrees + Decimal(rng.randint(-4000, 4000)) / 100_000


def _documents(profile: Profile, kyc: KycProfile, rng: random.Random) -> list[KycDocument]:
    if kyc.pan_token is None:
        return []
    types = [KycDocumentType.PAN_CARD, KycDocumentType.SELFIE, KycDocumentType.SIGNATURE]
    if kyc.aadhaar_ref_token is not None:
        types.insert(1, KycDocumentType.AADHAAR_MASKED)
    if kyc.ovd_type is OvdType.PASSPORT:
        types.append(KycDocumentType.PASSPORT)
    if kyc.ovd_type in (OvdType.VOTER_ID, OvdType.DRIVING_LICENCE):
        types.append(KycDocumentType.ADDRESS_PROOF)
    documents: list[KycDocument] = []
    uploaded = kyc.created_at + timedelta(minutes=2)
    for doc_type in types:
        if rng.random() < 0.06:
            documents.append(_document(profile, kyc, rng, doc_type, uploaded, rejected=True))
            uploaded += timedelta(minutes=rng.randint(2, 30))
        documents.append(_document(profile, kyc, rng, doc_type, uploaded, rejected=False))
        uploaded += timedelta(minutes=1)
    return documents


def _document(
    profile: Profile,
    kyc: KycProfile,
    rng: random.Random,
    doc_type: KycDocumentType,
    uploaded: datetime,
    *,
    rejected: bool,
) -> KycDocument:
    document_id = new_id(IdPrefix.KYC_DOCUMENT, at=uploaded, rng=rng)
    key = f"kyc/{profile.customer_id}/{document_id}-{doc_type.value}.jpg"
    expires = (
        date(uploaded.year + rng.randint(2, 9), uploaded.month, 1)
        if doc_type is KycDocumentType.PASSPORT
        else None
    )
    return KycDocument(
        document_id=document_id,
        kyc_id=kyc.kyc_id,
        customer_id=profile.customer_id,
        doc_type=doc_type,
        s3_key=key,
        sha256=refs.sha256_of(key),
        status=KycDocumentStatus.REJECTED if rejected else KycDocumentStatus.ACCEPTED,
        rejection_reason="Image blurred; details unreadable" if rejected else None,
        uploaded_at=uploaded,
        expires_on=expires,
    )


def screening_rows(
    config: GenerationConfig, profile: Profile, rng: random.Random
) -> list[ScreeningResult]:
    """Screened at onboarding, and again each year the relationship lasts into the window."""
    instants = [profile.onboarded_at]
    while (next_at := instants[-1] + timedelta(days=365)) < config.now:
        instants.append(next_at)
    results: list[ScreeningResult] = []
    for at in instants:
        if profile.pep:
            source, score, decision = ListSource.INTERNAL_PEP, _score(rng, 92, 99), "true"
        elif rng.random() < 0.03:
            source = pick(rng, _HIT_LISTS)
            score, decision = _score(rng, 70, 88), "potential"
        else:
            source, score, decision = rng.choice(list(ListSource)), _score(rng, 0, 35), "clear"
        results.append(
            ScreeningResult(
                screening_id=new_id(IdPrefix.SCREENING, at=at, rng=rng),
                customer_id=profile.customer_id,
                screened_name=profile.full_name,
                list_source=source,
                match_score=score,
                decision={
                    "true": ScreeningDecision.TRUE_MATCH,
                    "potential": ScreeningDecision.POTENTIAL_MATCH,
                    "clear": ScreeningDecision.CLEAR,
                }[decision],
                vendor_ref=f"SCR-{at:%Y%m%d}-{refs.digits(rng, 6)}",
                screened_at=at,
            )
        )
    return results
