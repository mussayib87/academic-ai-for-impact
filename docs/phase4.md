# Phase 4: Student Support Intelligence

The production risk model remains the authoritative signal. Phase 4 consumes the verified student risk and SHAP evidence to build a support workflow that is educational, reviewable, and auditable.

## What is included

- Student support profile endpoint using the existing production risk prediction and explanation evidence.
- Personalized recommendation output based on the current risk level and top risk drivers.
- Support action creation for teacher-led academic follow-up work.
- Follow-up scheduling for support tracking and student support continuity.
- Student-level access control so a student can only view their own support profile.

## Key API surfaces

- GET /api/v1/students/{student_id}/support-profile
- GET /api/v1/students/{student_id}/support-plan
- GET /api/v1/students/{student_id}/support-timeline
- GET /api/v1/students/{student_id}/support-actions
- POST /api/v1/students/{student_id}/support-actions
- POST /api/v1/interventions/{student_id}/follow-up

## Safety boundaries

- Existing model training, deployment, and validation flows are not modified.
- Support actions are evidence-grounded, not predictive replacements.
- Recommendations are generated from actual risk and explanation data rather than fabricated information.
