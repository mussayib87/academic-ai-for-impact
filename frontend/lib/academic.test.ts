import { describe, expect, it } from 'vitest';
import { getAssignmentStatus } from './academic';

describe('getAssignmentStatus', () => {
  it('distinguishes pending work from published coursework', () => {
    expect(getAssignmentStatus('active')).toBe('Pending');
    expect(getAssignmentStatus('draft')).toBe('Active');
  });

  it('reflects submission and grading states', () => {
    expect(getAssignmentStatus('active', 'submitted')).toBe('Submitted');
    expect(getAssignmentStatus('active', 'late')).toBe('Late');
    expect(getAssignmentStatus('active', 'graded')).toBe('Completed');
  });
});