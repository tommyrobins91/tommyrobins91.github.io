"""One call from OM claims to a finished audit."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .claims import OMClaims
from .profile import PropertyProfile, build_profile
from .rules import HIGH, MEDIUM, Flag, run_rules
from .underwrite import Underwriting, underwrite


@dataclass
class Audit:
    claims: OMClaims
    profile: PropertyProfile
    flags: List[Flag]
    uw: Underwriting

    @property
    def high(self) -> List[Flag]:
        return [f for f in self.flags if f.severity == HIGH]

    @property
    def medium(self) -> List[Flag]:
        return [f for f in self.flags if f.severity == MEDIUM]

    @property
    def noi_gap(self) -> Optional[float]:
        """OM's headline NOI minus our adjusted NOI on the same basis."""
        if self.uw.om_noi_basis is None or self.uw.adjusted_noi_basis is None:
            return None
        return self.uw.om_noi_basis - self.uw.adjusted_noi_basis

    @property
    def price_gap(self) -> Optional[float]:
        if self.uw.value_at_om_cap is None or not self.claims.asking_price:
            return None
        return self.claims.asking_price - self.uw.value_at_om_cap

    @property
    def grade(self) -> str:
        score = len(self.high) * 3 + len(self.medium)
        if score == 0:
            return "A"
        if score <= 2:
            return "B"
        if score <= 5:
            return "C"
        if score <= 9:
            return "D"
        return "F"


def analyze(claims: OMClaims, profile: Optional[PropertyProfile] = None) -> Audit:
    if profile is None:
        profile = build_profile(address=claims.address, bbl=claims.bbl)
    return Audit(claims, profile, run_rules(claims, profile), underwrite(claims, profile))
