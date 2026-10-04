export type AssignmentStatus = 'Active' | 'Pending' | 'Submitted' | 'Late' | 'Completed';

export function getAssignmentStatus(assignmentStatus: string, submissionStatus?: string | null): AssignmentStatus {
  if (submissionStatus === 'graded') return 'Completed';
  if (submissionStatus === 'late') return 'Late';
  if (submissionStatus === 'submitted') return 'Submitted';
  return assignmentStatus === 'active' ? 'Pending' : 'Active';
}