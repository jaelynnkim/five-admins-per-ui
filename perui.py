import streamlit as st
import smtplib
import imaplib
from email.message import EmailMessage
from simple_salesforce import Salesforce, SalesforceLogin
import os
from datetime import datetime, timedelta
import random

st.set_page_config(page_title="Request Form", page_icon="📝")

if "passkey_accepted" not in st.session_state:
    st.session_state["passkey_accepted"] = False

# Salesforce credentials
SF_USERNAME = os.getenv("SF_USERNAME")
SF_PASSWORD = os.getenv("SF_PASSWORD")
SF_SECURITY_TOKEN = os.getenv("SF_SECURITY_TOKEN")
SF_DOMAIN = 'test'

# Connect to Salesforce
try:
    session_id, instance = SalesforceLogin(
        username=SF_USERNAME, 
        password=SF_PASSWORD, 
        security_token=SF_SECURITY_TOKEN, 
        domain=SF_DOMAIN
    )
    sf = Salesforce(session_id=session_id, instance=instance)
except Exception as e:
    st.error(f"Failed to connect to Salesforce: {e}")

# Define a dictionary of Contact IDs with the corresponding passkeys
CONTACT_PASSKEYS = {
    "003ca000003iFIJAA2": {"name": "Lizette Bullock", "passkey": None},
    "003ca000003iFIOAA2": {"name": "Melissa Schneider", "passkey": None},
    "003ca000003iElNAAU": {"name": "Kevin Kelley", "passkey": None},
    "003ca000003iJbpAAE": {"name": "Molly Parmeter", "passkey": None},
    "003ca000003iJh6AAE": {"name": "Jae Kim", "passkey": None}
}

# Function to generate a random secret word
def generate_secret_word():
    words = ["apple", "bird", "cat", "dog", "elephant", "fish", "grape", "hat", "ice", "jungle", 
             "kite", "lemon", "moon", "nest", "orange", "penguin", "queen", "rain", "sun", 
             "tree", "umbrella", "vase", "wind", "xylophone", "yarn", "zebra"]
    return ''.join(random.sample(words, 3))

# Function to retrieve the secret word for all administrators
def load_secret_words():
    for contact_id in CONTACT_PASSKEYS:
        try:
            contact = sf.Contact.get(contact_id)
            secret_word = contact.get('PER_Form_Secret_Word__c')
            last_changed_date = contact.get('PER_Form_Secret_Changed_Date__c')
            CONTACT_PASSKEYS[contact_id]["passkey"] = secret_word
            CONTACT_PASSKEYS[contact_id]["last_changed"] = last_changed_date
        except Exception as e:
            st.error(f"Failed to load secret word for contact {CONTACT_PASSKEYS[contact_id]['name']}: {e}")

# Function to safely parse the datetime from Salesforce
def parse_salesforce_datetime(last_changed):
    try:
        return datetime.strptime(last_changed, '%Y-%m-%dT%H:%M:%S.%fZ')
    except ValueError:
        return datetime.strptime(last_changed.split('.')[0] + 'Z', '%Y-%m-%dT%H:%M:%SZ')

# Function to save the secret word for a specific contact
def save_secret_word(contact_id, secret_word):
    try:
        sf.Contact.update(contact_id, {
            'PER_Form_Secret_Word__c': secret_word,
            'PER_Form_Secret_Changed_Date__c': datetime.now().isoformat()
        })
    except Exception as e:
        st.error(f"Failed to save secret word for contact {CONTACT_PASSKEYS[contact_id]['name']}: {e}")

# Function to update secret words if more than 3 months have passed
def update_secret_words_if_needed():
    for contact_id, details in CONTACT_PASSKEYS.items():
        last_changed = details.get("last_changed")
        if not details["passkey"] or last_changed is None or (
            datetime.now() - parse_salesforce_datetime(last_changed) > timedelta(days=90)
        ):
            new_secret_word = generate_secret_word()
            save_secret_word(contact_id, new_secret_word)
            details["passkey"] = new_secret_word

# Load secret words from Salesforce and update if needed
load_secret_words()
update_secret_words_if_needed()

# Get the passkey input from the user
passkey_input = st.text_input("Enter the passkey provided to you:", type="password")

# Validate the passkey and identify the administrator
administrator_name = None
contact_id = None
for cid, details in CONTACT_PASSKEYS.items():
    if passkey_input == details["passkey"]:
        administrator_name = details["name"]
        contact_id = cid
        break

# State to track whether the passkey has been accepted
if administrator_name:
    st.session_state["passkey_accepted"] = True
    st.success(f"Access granted by {administrator_name}!")
else:
    if passkey_input:
        st.error("Incorrect passkey. Please try again.")

# If passkey is accepted, display the form
if st.session_state.get("passkey_accepted"):
    st.write(f"Access granted by {administrator_name}.")
    st.write("All fields are required. If you do not have an answer for a field, please enter N/A.")
    
    with st.form(key='request_form'):
        first_name = st.text_input("First Name")
        middle_name = st.text_input("Middle Name")
        last_name = st.text_input("Last Name")
        preferred_email = st.text_input("Preferred Email Address")
        job_title = st.text_input("Job Title")
        practice_name = st.text_input("Practice Name")
        practice_address = st.text_input("Practice Address")
        supervisor_name = st.text_input("Supervisor Full Name")
        reasoning = st.text_area("Reasoning behind Request")
        
        has_urmc_account = st.radio(
            "Already have URMC account for eRecords or prior engagement?",
            options=["Yes", "No"]
        )

        submit_button = st.form_submit_button(label='Submit')

        if submit_button:
            # Validate fields and prepare to create a Case in Salesforce
            fields = [first_name, middle_name, last_name, preferred_email, job_title, practice_name, practice_address, supervisor_name, reasoning]
            if any(field.strip() == "" for field in fields):
                st.error("All fields are required. Please enter N/A if a field does not apply.")
            else:
                try:
                    contact_query = f"SELECT Id, AccountId FROM Contact WHERE FirstName = '{first_name}' AND LastName = '{last_name}' LIMIT 1"
                    contact_result = sf.query(contact_query)
    
                    contact_id = None
                    account_id = None
    
                    if contact_result['totalSize'] > 0:
                        contact_id = contact_result['records'][0]['Id']
                        account_id = contact_result['records'][0]['AccountId']
                        
                    case_data = {
                        'RecordTypeId': '012Dn000000FGWvIAO',
                        'Team__c': 'Information Services',
                        'Case_Type__c': 'System Access Request',
                        'Case_Type_Specific__c': 'PER',
                        'Estimated_Start_Date__c': datetime.now().date().isoformat(),
                        'System__c': 'PER',
                        'Severity__c': 'Individual',
                        'Effort__c': 'Low',
                        'Status': 'New',
                        'Priority': 'Medium',
                        'Reason': 'New problem',
                        'Origin': 'Web',
                        'SuppliedName': 'PER Web to Case Form',
                        'Subject': f"{first_name} {last_name} PER Request Form",
                        'Description': (
                            f"First Name: {first_name}\n"
                            f"Middle Name: {middle_name}\n"
                            f"Last Name: {last_name}\n"
                            f"Preferred Email Address: {preferred_email}\n"
                            f"Job Title: {job_title}\n"
                            f"Practice Name: {practice_name}\n"
                            f"Practice Address: {practice_address}\n"
                            f"Supervisor Full Name: {supervisor_name}\n"
                            f"Reasoning behind Request: {reasoning}\n"
                            f"Already have URMC account: {has_urmc_account}\n"
                            f"Form access granted by: {administrator_name}"
                        )
                    }
    
                    if contact_id:
                        case_data['ContactId'] = contact_id
                    if account_id:
                        case_data['AccountId'] = account_id
    
                    case = sf.Case.create(case_data)
                    
                    st.success("Form submitted successfully and Case created in Salesforce!")
                except Exception as e:
                    st.error(f"Failed to create Case in Salesforce: {e}")
