import { NextRequest, NextResponse } from 'next/server'
import { writeFileSync, readFileSync, existsSync, mkdirSync, unlinkSync, statSync } from 'fs'
import { join } from 'path'
import { tmpdir } from 'os'

export async function GET(request: NextRequest) {
  const testResults: any = {
    timestamp: new Date().toISOString(),
    tests: [],
    overall_status: 'pending'
  }

  try {
    const testDir = join(tmpdir(), 'writerbloom-file-test')
    const testFile = join(testDir, 'test-file.txt')
    const testContent = `Test file created at ${new Date().toISOString()}`

    // Test 1: Directory Creation
    try {
      if (!existsSync(testDir)) {
        mkdirSync(testDir, { recursive: true })
      }
      testResults.tests.push({
        name: 'Directory Creation',
        status: 'passed',
        message: 'Successfully created test directory'
      })
    } catch (error: any) {
      testResults.tests.push({
        name: 'Directory Creation',
        status: 'failed',
        message: error.message
      })
    }

    // Test 2: File Writing
    try {
      writeFileSync(testFile, testContent, 'utf8')
      testResults.tests.push({
        name: 'File Writing',
        status: 'passed',
        message: 'Successfully wrote test file'
      })
    } catch (error: any) {
      testResults.tests.push({
        name: 'File Writing',
        status: 'failed',
        message: error.message
      })
    }

    // Test 3: File Reading
    try {
      const readContent = readFileSync(testFile, 'utf8')
      if (readContent === testContent) {
        testResults.tests.push({
          name: 'File Reading',
          status: 'passed',
          message: 'Successfully read and verified test file'
        })
      } else {
        testResults.tests.push({
          name: 'File Reading',
          status: 'failed',
          message: 'File content mismatch'
        })
      }
    } catch (error: any) {
      testResults.tests.push({
        name: 'File Reading',
        status: 'failed',
        message: error.message
      })
    }

    // Test 4: File Stats
    try {
      const stats = statSync(testFile)
      testResults.tests.push({
        name: 'File Stats',
        status: 'passed',
        message: `File size: ${stats.size} bytes, modified: ${stats.mtime.toISOString()}`
      })
    } catch (error: any) {
      testResults.tests.push({
        name: 'File Stats',
        status: 'failed',
        message: error.message
      })
    }

    // Test 5: Chapter Directory Check
    try {
      const projectRoot = process.cwd()
      const chaptersDir = join(projectRoot, 'chapters')
      
      if (existsSync(chaptersDir)) {
        const stats = statSync(chaptersDir)
        testResults.tests.push({
          name: 'Chapters Directory Access',
          status: 'passed',
          message: `Chapters directory exists and is accessible (${stats.isDirectory() ? 'directory' : 'file'})`
        })
      } else {
        testResults.tests.push({
          name: 'Chapters Directory Access',
          status: 'warning',
          message: 'Chapters directory does not exist (will be created when needed)'
        })
      }
    } catch (error: any) {
      testResults.tests.push({
        name: 'Chapters Directory Access',
        status: 'failed',
        message: error.message
      })
    }

    // Test 6: Cleanup
    try {
      if (existsSync(testFile)) {
        unlinkSync(testFile)
      }
      testResults.tests.push({
        name: 'File Cleanup',
        status: 'passed',
        message: 'Successfully cleaned up test file'
      })
    } catch (error: any) {
      testResults.tests.push({
        name: 'File Cleanup',
        status: 'failed',
        message: error.message
      })
    }

    // Determine overall status
    const failedTests = testResults.tests.filter((test: any) => test.status === 'failed')
    const warningTests = testResults.tests.filter((test: any) => test.status === 'warning')
    
    if (failedTests.length === 0) {
      testResults.overall_status = warningTests.length > 0 ? 'warning' : 'passed'
    } else {
      testResults.overall_status = 'failed'
    }

    testResults.summary = {
      total: testResults.tests.length,
      passed: testResults.tests.filter((test: any) => test.status === 'passed').length,
      failed: failedTests.length,
      warnings: warningTests.length
    }

    return NextResponse.json(testResults)

  } catch (error: any) {
    console.error('File operations test error:', error)
    return NextResponse.json(
      {
        timestamp: new Date().toISOString(),
        overall_status: 'error',
        error: error.message,
        tests: testResults.tests
      },
      { status: 500 }
    )
  }
} 