'use client'

import CompanionView from '@/components/CompanionView'

export default function PersonalPage() {
  return (
    <CompanionView
      defaultAudience="cared_for"
      viewLabel="personal"
      otherRoute={{ href: '/caregiver', label: 'Caregiver view →' }}
    />
  )
}
