# -*- coding: utf-8 -*-
import json
import logging
from fhirclient import client
from fhirclient.models.medication import Medication
from fhirclient.models.medicationrequest import MedicationRequest
import fhirclient.models.patient as pat
import fhirclient.models.procedure as proc
import fhirclient.models.medicationrequest as med_st
import fhirclient.models.medication as med
import fhirclient.models.observation as obs
import fhirclient.models.fhirdate as date
from flask import Flask, request, redirect, session, render_template


# app setup
smart_defaults = {
    'app_id': 'my_web_app',
    'api_base': 'http://localhost:8080/baseDstu3/',
    'redirect_uri': 'http://localhost:8000/fhir-app/',
}

app = Flask(__name__)

def resolveData(p):
    try:
        date = p.performedPeriod.start.date
        p_type = 'long'
    except:
        date = p.performedDateTime.date
        p_type = 'short'
    return date, p_type

def resolveUnits(o):
    try:
        units = o.valueQuantity.unit
        value = o.valueQuantity.value
    except:
        try:
            value = o.valueCodeableConcept.text
        except:
            value = ''
        units =''
    return value, units

def _save_state(state):
    session['state'] = state

def _get_smart():
    state = session.get('state')
    print("State: ", state)
    if state:
        return client.FHIRClient(state=state, save_func=_save_state)
    else:
        return client.FHIRClient(settings=smart_defaults, save_func=_save_state)

def _logout():
    if 'state' in session:
        smart = _get_smart()
        smart.reset_patient()

def _reset():
    if 'state' in session:
        del session['state']

def _get_prescriptions(smart):
    bundle = MedicationRequest.where({'patient': smart.patient_id}).perform(smart.server)
    pres = [be.resource for be in bundle.entry] if bundle is not None and bundle.entry is not None else None
    if pres is not None and len(pres) > 0:
        return pres
    return None

def _get_medication_by_ref(ref, smart):
    med_id = ref.split("/")[1]
    return Medication.read(med_id, smart.server).code

def _med_name(med):
    if med.coding:
        name = next((coding.display for coding in med.coding if coding.system == 'http://www.nlm.nih.gov/research/umls/rxnorm'), None)
        if name:
            return name
    if med.text and med.text:
        return med.text
    return "Unnamed Medication(TM)"

def _get_med_name(prescription, client=None):
    if prescription.medicationCodeableConcept is not None:
        med = prescription.medicationCodeableConcept
        return _med_name(med)
    elif prescription.medicationReference is not None and client is not None:
        med = _get_medication_by_ref(prescription.medicationReference.reference, client)
        return _med_name(med)
    else:
        return 'Error: medication not found'


@app.route('/', methods=['POST', "GET"])
@app.route('/index.html', methods=['POST', "GET"])
def index():
    passed_patients = []
    smart = _get_smart()
    if request.method == 'POST' and request.form['text'] != '':
        header = "Results for name: " + request.form['text']
        full_name = request.form['text'].split(' ')
        search = pat.Patient.where(struct={'family': full_name[1], 'given':  full_name[0]})
        patients = search.perform_resources(smart.server)
        if len(patients) == 0:
            search = pat.Patient.where(struct={'family': full_name[0], 'given': full_name[1]})
            patients = search.perform_resources(smart.server)
        patients = [a for a in patients if a.name[0].family == full_name[1] or a.name[0].family == full_name[0]]
    else:
        header = "List of patients"
        search = pat.Patient.where(struct={})
        patients = search.perform_resources(smart.server)
    for i, patient in enumerate(patients):
        search_proc = proc.Procedure.where(struct={'patient': patient.id})
        procedures = search_proc.perform_resources(smart.server)

        search_med_st = med_st.MedicationRequest.where(struct={'patient':  patient.id})
        med_statments = search_med_st.perform_resources(smart.server)

        search_obs = obs.Observation.where(struct={'patient':  patient.id})
        observations = search_obs.perform_resources(smart.server)

        # search_med = med.Medication.where(struct={'patient':  patient.id})
        # medications = search_med.perform_resources(smart.server)

        passed_patients.append({
            'name': patient.name[0].family,
            'surname': patient.name[0].given[0],
            'procedures': sorted([{
                'name': p.extension[0].valueCodeableConcept.coding[0].display,
                'startDate': resolveData(p)[0],
                'type': resolveData(p)[1],
                'id': p.id
            } for p in procedures],
                key=lambda k: k['startDate']),
            'observations': sorted([{
                'name': o.code.coding[0].display,
                'startDate': o.effectiveDateTime.date,
                'status': o.status,
                'units': resolveUnits(o)[1],
                'value': resolveUnits(o)[0],
                'id': o.id
            } for o in observations],
                key=lambda k: k['startDate']),
            'med_requests': sorted([{
                'name': m.medicationCodeableConcept.coding[0].display,
                'startDate': m.authoredOn.date,
                'id': m.id
            } for m in med_statments],
                key=lambda k: k['startDate']),
        })
    return render_template('index.html', patients=passed_patients, header=header)


@app.route('/fhir-app/')
def callback():
    """ OAuth2 callback interception.
    """
    smart = _get_smart()
    try:
        smart.handle_callback(request.url)
    except Exception as e:
        return """<h1>Authorization Error</h1><p>{0}</p><p><a href="/">Start over</a></p>""".format(e)
    return redirect('/')


@app.route('/logout')
def logout():
    _logout()
    return redirect('/')


@app.route('/reset')
def reset():
    _reset()
    return redirect('/')


# start the app
if '__main__' == __name__:
    import flaskbeaker
    flaskbeaker.FlaskBeaker.setup_app(app)
    
    logging.basicConfig(level=logging.DEBUG)
    app.run(debug=True, port=8000)
