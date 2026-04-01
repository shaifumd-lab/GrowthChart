"""Clinical computation modules for GrowthChart v2.

Phases 12-16:
- mph: Mid-parental height calculation
- bayley_pinneau: Predicted adult height from bone age
- velocity: Growth velocity computation
- syndromic: Syndromic growth chart reference data (Turner, Down)
"""

from clinical.mph import calculate_mph, target_height_range
from clinical.bayley_pinneau import predict_adult_height
from clinical.velocity import compute_velocity
from clinical.syndromic import get_syndromic_percentile_curves, SUPPORTED_SYNDROMES
