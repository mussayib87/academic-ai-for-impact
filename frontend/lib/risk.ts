export function formatRiskProbability(riskLevel: string, riskProbability: number): string {
  return `${Math.round(riskProbability * 100)}% P(${riskLevel})`;
}