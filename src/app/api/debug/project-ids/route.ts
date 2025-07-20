import { NextResponse } from 'next/server'

export async function GET() {
  try {
    // Get client-side project ID
    const clientProjectId = process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID
    
    // Get admin-side project ID from service account
    let adminProjectId = null
    let serviceAccountInfo = null
    
    try {
      const serviceAccountJson = process.env.SERVICE_ACCOUNT_JSON
      if (serviceAccountJson) {
        const serviceAccount = JSON.parse(serviceAccountJson)
        adminProjectId = serviceAccount.project_id
        serviceAccountInfo = {
          project_id: serviceAccount.project_id,
          client_email: serviceAccount.client_email,
          private_key_id: serviceAccount.private_key_id
        }
      }
    } catch (parseError) {
      console.error('Error parsing service account:', parseError)
    }
    
    const projectMatch = clientProjectId === adminProjectId
    
    return NextResponse.json({
      clientProjectId,
      adminProjectId,
      projectMatch,
      serviceAccountInfo,
      diagnosis: projectMatch 
        ? "✅ Project IDs match - this is not the issue"
        : "❌ PROJECT ID MISMATCH - This is likely causing the auth/configuration-not-found error"
    })
    
  } catch (error) {
    return NextResponse.json({
      error: 'Failed to check project IDs',
      details: error.message
    }, { status: 500 })
  }
} 