from collections.abc import Sequence
from math import sqrt
from typing import Any


def calculate_momentum(values: Sequence[float], minimum_observations: int = 4) -> dict[str, Any]:
    observations = [float(value) for value in values]
    if len(observations) < minimum_observations:
        return {
            'classification': 'INSUFFICIENT_DATA',
            'observation_count': len(observations),
            'recent_average': None,
            'historical_average': None,
            'trend_slope': None,
            'percent_change': None,
        }

    split = len(observations) // 2
    historical = observations[:split]
    recent = observations[split:]
    historical_average = sum(historical) / len(historical)
    recent_average = sum(recent) / len(recent)
    x_mean = (len(observations) - 1) / 2
    y_mean = sum(observations) / len(observations)
    denominator = sum((index - x_mean) ** 2 for index in range(len(observations)))
    slope = sum((index - x_mean) * (value - y_mean) for index, value in enumerate(observations)) / denominator
    percent_change = ((recent_average - historical_average) / abs(historical_average) * 100) if historical_average else None
    differences = [right - left for left, right in zip(observations, observations[1:])]
    diff_mean = sum(differences) / len(differences)
    volatility = sqrt(sum((item - diff_mean) ** 2 for item in differences) / len(differences))
    scale = max(abs(y_mean), 1)
    if volatility > scale * 0.3:
        classification = 'VOLATILE'
    elif slope > scale * 0.015 and (percent_change is None or percent_change > 5):
        classification = 'IMPROVING'
    elif slope < -scale * 0.015 and (percent_change is None or percent_change < -5):
        classification = 'DECLINING'
    else:
        classification = 'STABLE'
    return {
        'classification': classification,
        'observation_count': len(observations),
        'recent_average': recent_average,
        'historical_average': historical_average,
        'trend_slope': slope,
        'percent_change': percent_change,
        'volatility': volatility,
    }