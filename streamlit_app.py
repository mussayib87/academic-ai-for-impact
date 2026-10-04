import os

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st


st.set_page_config(page_title='Academic AI for Impact | Research demo', page_icon='A', layout='wide')
st.title('Academic AI for Impact')
st.caption('Research and demonstration interface · fictional or institution-authorized records only')

api_url = st.sidebar.text_input('FastAPI URL', os.getenv('ACADEMIC_AI_API_URL', 'http://127.0.0.1:8000')).rstrip('/')


def request_api(method: str, path: str, *, token: str, **kwargs):
    response = requests.request(
        method,
        f'{api_url}{path}',
        headers={'Authorization': f'Bearer {token}'},
        timeout=30,
        **kwargs,
    )
    try:
        payload = response.json()
    except ValueError:
        payload = {'detail': response.text}
    if not response.ok:
        detail = payload.get('detail', f'API request failed ({response.status_code})')
        if isinstance(detail, dict):
            detail = detail.get('message', str(detail))
        raise RuntimeError(str(detail))
    return payload


with st.sidebar.form('faculty-login'):
    st.subheader('Faculty sign-in')
    email = st.text_input('Email', value='teacher@example.com')
    password = st.text_input('Password', type='password')
    submitted = st.form_submit_button('Connect')
    if submitted:
        try:
            login = requests.post(
                f'{api_url}/api/v1/auth/login',
                json={'email': email, 'password': password},
                timeout=15,
            )
            login.raise_for_status()
            profile = login.json()['user']
            if profile['role'] != 'TEACHER':
                raise RuntimeError('Teacher access is required for this demonstration.')
            st.session_state['academic_ai_token'] = login.json()['access_token']
            st.session_state['academic_ai_email'] = email
        except (requests.RequestException, KeyError, RuntimeError, ValueError) as exc:
            st.sidebar.error(str(exc))

token = st.session_state.get('academic_ai_token')
if not token:
    st.info('Sign in with an authorized faculty account to load risk, academic, and intervention evidence.')
    st.stop()

try:
    monitoring = request_api('GET', '/api/v1/risk/monitoring', token=token)
    demo = request_api('GET', '/api/v1/risk/high-risk-demo', token=token)
    page = request_api('GET', '/api/v1/students?limit=100&offset=0&sort=full_name', token=token)
    directory = list(page['items'])
    for offset in range(100, page['total'], 100):
        directory.extend(request_api('GET', f'/api/v1/students?limit=100&offset={offset}&sort=full_name', token=token)['items'])
except (requests.RequestException, RuntimeError) as exc:
    st.error(str(exc))
    st.stop()

st.subheader('Current class risk distribution')
distribution_columns = st.columns(3)
for column, level in zip(distribution_columns, ('HIGH', 'MEDIUM', 'LOW')):
    column.metric(level, monitoring['distribution'].get(level, 0))
st.bar_chart(pd.DataFrame([monitoring['distribution']]), height=120)

students_by_id = {item['id']: item for item in directory}
demo_student = demo['student']
students_by_id.setdefault(demo_student['id'], demo_student)
student_ids = list(students_by_id)
default_index = student_ids.index(demo_student['id'])
selected_id = st.selectbox(
    'Student',
    student_ids,
    index=default_index,
    format_func=lambda student_id: f"{students_by_id[student_id]['full_name']} · {students_by_id[student_id]['student_id']}",
)

try:
    selected = demo if selected_id == demo_student['id'] else request_api('GET', f'/api/v1/students/{selected_id}/explanation', token=token)
    momentum = request_api('GET', f'/api/v1/students/{selected_id}/momentum', token=token)
except (requests.RequestException, RuntimeError) as exc:
    st.error(str(exc))
    st.stop()

student = selected['student']
prediction = selected['prediction']
explanation = selected['explanation']
features = selected['features']
st.subheader(f"{student['full_name']} · {student['student_id']}")
if not demo['high_risk_available'] and selected_id == demo_student['id']:
    st.warning(demo['selection_note'])

risk_columns = st.columns(4)
risk_columns[0].metric('Canonical risk level', prediction['risk_level'])
risk_columns[1].metric(f"P({prediction['risk_level']})", f"{prediction['risk_probability']:.1%}")
risk_columns[2].metric('Model version', prediction['model_version'])
risk_columns[3].metric('Explanation target', explanation['target'])
st.caption('Class probabilities are the model output. Risk class is argmax(class_probabilities); no UI threshold or relabeling is applied.')
st.json(prediction['class_probabilities'], expanded=True)

left, right = st.columns([1, 1])
with left:
    st.markdown('#### Academic indicators')
    feature_frame = pd.DataFrame([{'Feature': name.replace('_', ' '), 'Value': value} for name, value in features.items()])
    st.dataframe(feature_frame, hide_index=True, use_container_width=True)
with right:
    st.markdown('#### SHAP contributions')
    explanation_values = explanation['waterfall']
    measures = ['absolute'] + ['relative'] * len(explanation_values) + ['total']
    labels = ['Base value'] + [item['feature'].replace('_', ' ') for item in explanation_values] + [explanation['target']]
    values = [explanation['base_value']] + [item['contribution'] for item in explanation_values] + [0]
    figure = go.Figure(go.Waterfall(
        orientation='v',
        measure=measures,
        x=labels,
        y=values,
        connector={'line': {'color': '#8391a2'}},
        increasing={'marker': {'color': '#d45c55'}},
        decreasing={'marker': {'color': '#3caa79'}},
        totals={'marker': {'color': '#3a9da0'}},
    ))
    figure.update_layout(title=f"SHAP waterfall · {explanation['target']}", height=430, margin={'l': 10, 'r': 10, 't': 55, 'b': 100}, showlegend=False, yaxis_title='Probability contribution', xaxis={'tickangle': -35})
    st.plotly_chart(figure, use_container_width=True)
    st.caption('Waterfall target matches the canonical prediction class.')

st.markdown('#### Momentum indicators')
momentum_metrics = momentum.get('metrics', {})
if momentum_metrics:
    momentum_columns = st.columns(min(4, len(momentum_metrics)))
    for index, (metric, data) in enumerate(momentum_metrics.items()):
        percent_change = data.get('percent_change')
        change_label = f'{percent_change:.1f}% change' if percent_change is not None else f"{data['observation_count']} observations"
        momentum_columns[index % len(momentum_columns)].metric(metric.replace('_', ' ').title(), data['classification'], change_label)
else:
    st.info('No dated momentum observations are available for this student.')

st.markdown('#### Faculty intervention draft')
st.warning('Generated content is an AI draft. Faculty review and explicit approval are required before any intervention is sent.')
if st.button('Generate draft using configured provider'):
    try:
        draft = request_api('POST', '/api/v1/interventions/generate', token=token, json={'student_id': selected_id})
        st.session_state['academic_ai_last_draft'] = draft
    except (requests.RequestException, RuntimeError) as exc:
        st.error(str(exc))

draft = st.session_state.get('academic_ai_last_draft')
if draft and draft.get('student_id') == selected_id:
    st.caption(f"Provider: {draft['provider']} · Status: {draft['status']}")
    st.text_area('Draft for faculty review', value=draft['body'], height=220, disabled=True)
    st.info('Review and approve this draft in the Academic AI faculty workspace before it is delivered.')
