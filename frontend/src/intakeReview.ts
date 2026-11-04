export type IntakeReview = {
  text: string; originalText: string; source: string; claim: string
  sourceNote: string; context: string; creatingContext: boolean
}

export function editedFilePreview(review: Pick<IntakeReview, 'text' | 'originalText' | 'source'>): boolean {
  return Boolean(review.source) && review.text !== review.originalText
}

export function hasPendingIntakeReview(review: IntakeReview): boolean {
  return Boolean(review.claim.trim() || review.sourceNote.trim() || review.context || review.creatingContext
    || editedFilePreview(review) || (!review.source && review.text.trim()))
}

export function samePreview(review: Pick<IntakeReview, 'text' | 'source'>, text: string, source: string): boolean {
  return review.text === text && review.source === source
}
