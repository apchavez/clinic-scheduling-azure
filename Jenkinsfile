// Jenkins Declarative Pipeline equivalent of .github/workflows/ci.yml.
// Kept alongside GitHub Actions (the CI actually enforced on this repo) to demonstrate
// Jenkinsfile/Groovy DSL fluency for orgs that run Jenkins on-prem instead of a SaaS CI.
pipeline {
    agent any

    environment {
        SONAR_TOKEN = credentials('sonar-token')
    }

    options {
        timestamps()
        disableConcurrentBuilds()
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Trivy vulnerability scan') {
            steps {
                sh '''
                    trivy fs --scanners vuln --severity CRITICAL,HIGH \
                        --exit-code 1 --ignore-unfixed --format table .
                '''
            }
        }

        stage('Install dependencies') {
            steps {
                sh 'pip install -r requirements-dev.txt'
            }
        }

        stage('Lint and format check') {
            steps {
                sh '''
                    ruff format --check .
                    ruff check .
                '''
            }
        }

        stage('Test with coverage') {
            steps {
                sh '''
                    pytest --cov=clinic --cov-report=xml --cov-report=term --junitxml=test-results.xml
                    coverage report --fail-under=80 --include="clinic/domain/*,clinic/application/*"
                '''
            }
        }

        stage('Lint Bicep IaC') {
            steps {
                sh '''
                    az bicep install
                    az bicep lint --file infra/main.bicep
                '''
            }
        }

        stage('Validate OpenAPI contract') {
            steps {
                sh 'npx --yes @redocly/cli lint src/docs/openapi.yaml'
            }
        }

        stage('SonarCloud analysis') {
            when {
                branch 'main'
            }
            steps {
                withSonarQubeEnv('SonarCloud') {
                    sh 'sonar-scanner'
                }
            }
        }
    }

    post {
        always {
            junit testResults: 'test-results.xml', allowEmptyResults: true
            archiveArtifacts artifacts: 'coverage.xml', allowEmptyArchive: true
        }
    }
}
