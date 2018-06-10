# -*- coding: utf-8 -*-
import json
import logging
from fhirclient import client
from fhirclient.models.medication import Medication
from fhirclient.models.medicationrequest import MedicationRequest
import fhirclient.models.patient as pat
import fhirclient.models.procedure as proc
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
    patient = pat.Patient.read('06eb35fc-09e6-48b4-a311-47633f6c4769', smart.server)
    if request.method == 'POST' and request.form['text'] != '':
        header = "Results for name: " + request.form['text']
        search = pat.Patient.where(struct={'family': request.form['text'].strip()})
        patients = search.perform_resources(smart.server)
        patients = [a for a in patients if a.name[0].family == request.form['text'].strip()]
        for i, patient in enumerate(patients):
            search_proc = proc.Procedure.where(struct={'patient': patient.id})
            procedures = search_proc.perform_resources(smart.server)
            patients[i] = (patient, procedures)
            passed_patients.append({
                'name': patient.name[0].family,
                'surname': patient.name[0].given[0],
                'procedures': [{
                    'name': p.extension[0].valueCodeableConcept.coding[0].display,
                    'startDate': resolveData(p)[0],
                    'type': resolveData(p)[1],
                    'id': p.id
                } for p in procedures]
            })
            for p in procedures:
                print(p.as_json())

        return render_template('index.html', patients=passed_patients, header=header)
    else:
        header = "Displaying male patients"
        search = pat.Patient.where(struct={'gender': 'male'})
        patients = search.perform_resources(smart.server)
        for i, patient in enumerate(patients):
            search_proc = proc.Procedure.where(struct={'patient': patient.id})
            procedures = search_proc.perform_resources(smart.server)
            patients[i] = (patient, procedures)
        return render_template('index.html', patients=patients, header=header)


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
