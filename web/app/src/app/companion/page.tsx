'use client'

import CompanionView from '@/components/CompanionView'

/**
 * The caregiver's view of one person.
 *
 * This route used to be a 442-line reimplementation of what `CompanionView`
 * already did for `/caregiver` — the same question, the same tier card, the
 * same reason list, differing mainly in chrome. Two copies of a safety-critical
 * screen is two places for the wording to drift, and `DEPLOYMENT.md` had
 * already stopped being able to describe which was which.
 *
 * `/caregiver` is gone; this is the one that survives.
 */
export default function CompanionPage() {
  return (
    <CompanionView
      defaultAudience="caregiver"
      viewLabel="caregiver"
      otherRoute={{ href: '/personal', label: 'Personal view →' }}
    />
  )
}
