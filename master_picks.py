# master_picks.py
# Consolidated list of all stocks provided by User

from user_picks import USER_PICKS
from user_picks_v2 import USER_PICKS_V2
from user_picks_v3 import USER_PICKS_V3
from user_picks_v4 import USER_PICKS_V4


MASTER_PICKS = sorted(list(set(USER_PICKS + USER_PICKS_V2 + USER_PICKS_V3 + USER_PICKS_V4)))
# Remove TATAMOTORS.NS if it's giving 404
if "TATAMOTORS.NS" in MASTER_PICKS:
    MASTER_PICKS.remove("TATAMOTORS.NS")
    # Adding TATAMOTORS.BO as a fallback if needed, but for now just focus on the working ones.
