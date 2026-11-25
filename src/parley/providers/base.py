"""
Base abstract provider interface.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime
from zoneinfo import ZoneInfo


class BaseProvider(ABC):
    """Abstract base class for sports data providers."""

    @abstractmethod
    def get_matches(self, fecha_str: str, tz: ZoneInfo, solo_futuros: bool = True) -> List[Dict[str, Any]]:
        """Fetch scheduled matches for a specific date in local timezone."""
        pass

    @abstractmethod
    def get_team_form(self, team_id: Any, cache: Dict[str, Any]) -> Optional[Dict[str, float]]:
        """Fetch recent form (goals for/against average) for a team."""
        pass
