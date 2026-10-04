import { describe, expect, it } from 'vitest';
import { formatRiskProbability } from './risk';

describe('formatRiskProbability', () => {
  it('formats the backend class and probability without reclassifying them', () => {
    const prediction = {
      risk_level: 'MEDIUM',
      risk_probability: 0.9949270346416472,
      class_probabilities: { HIGH: 0.0007082902259700415, LOW: 0.00436467513238273, MEDIUM: 0.9949270346416472 },
    };

    expect(formatRiskProbability(prediction.risk_level, prediction.risk_probability)).toBe('99% P(MEDIUM)');
  });
});