'use client'

import CompanionView from '@/components/CompanionView'

export default function CaregiverPage() {
  return (
    <CompanionView
      defaultAudience="caregiver"
      viewLabel="caregiver"
      otherRoute={{ href: '/personal', label: 'Personal view →' }}
    />
  )
}
