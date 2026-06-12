import re
with open('voice_agent/templates/voice_agent/dashboard.html', 'r', encoding='utf-8') as f:
    text = f.read()

hdr_old = '''                              <tr>
                                  <th>Patient Name</th>
                                  <th>Phone</th>
                                  <th>Appointment Class</th>
                                  <th>Booked Calendar Slot</th>
                                  <th>Log Outcome</th>
                                  <th>Support Contact</th>
                              </tr>'''
hdr_new = '''                              <tr>
                                  <th>Patient Name</th>
                                  <th>Phone</th>
                                  <th>Appointment Class</th>
                                  <th>Booked Calendar Slot</th>
                                  <th>Booking Status</th>
                                  <th>Actions</th>
                              </tr>'''

text = text.replace(hdr_old, hdr_new)

body_old = '''                              <tr>
                                  <td><strong>{{ app.first_name }} {{ app.last_name }}</strong></td>
                                  <td>{{ app.phone }}</td>
                                  <td>{{ app.appointment_type|default:"Cleaning Consult" }}</td>
                                  <td><span style="color: var(--success); font-weight: 700;">{{ app.selected_slot }}</span></td>
                                  <td>{{ app.call_outcome|default:"Booked" }}</td>
                                  <td>{{ app.support_person|default:"None" }}</td>
                              </tr>'''
body_new = '''                              <tr>
                                  <td><strong>{{ app.first_name }} {{ app.last_name }}</strong></td>
                                  <td>{{ app.phone }}</td>
                                  <td>{{ app.appointment_type|default:"Cleaning Consult" }}</td>
                                  <td><span style="color: var(--success); font-weight: 700;">{{ app.selected_slot }}</span></td>
                                  <td><span id="status-{{ app._id }}" style="text-transform: capitalize; font-weight:600;">{{ app.booking_status|default:"pending" }}</span></td>
                                  <td id="actions-{{ app._id }}">
                                      {% if app.booking_status != 'confirmed' and app.booking_status != 'declined' %}
                                      <button onclick="updateBooking('{{ app._id }}', 'confirmed')" class="btn-primary btn-blue" style="background-color:var(--success); color:white; border:none; padding:5px 10px; border-radius:5px; cursor:pointer;">Confirm</button>
                                      <button onclick="updateBooking('{{ app._id }}', 'declined')" class="btn-primary btn-blue" style="background-color:var(--danger); color:white; border:none; padding:5px 10px; border-radius:5px; cursor:pointer;">Decline</button>
                                      {% endif %}
                                  </td>
                              </tr>'''

text = text.replace('<td colspan="6"', '<td colspan="6"') # just in case, it's 6 cols still
text = text.replace(body_old, body_new)

js_new = '''    // Booking Update Function
    window.updateBooking = async function(patientId, status) {
        if (!confirm('Are you sure you want to mark this booking as ' + status + '?')) return;
        try {
            const resp = await fetch('/api/booking/update/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken') // ensure csrf
                },
                body: JSON.stringify({ patient_id: patientId, status: status })
            });
            const data = await resp.json();
            if (data.success) {
                document.getElementById('status-' + patientId).textContent = status;
                document.getElementById('actions-' + patientId).innerHTML = '';
            } else {
                alert('Error updating booking: ' + data.error);
            }
        } catch(e) {
            console.error(e);
            alert('Request failed.');
        }
    };
    
    // helper to get csrf token
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
'''

if 'window.updateBooking =' not in text:
    text = text.replace('// Testing Suite Dialer WebRTC Integration', js_new + '\n    // Testing Suite Dialer WebRTC Integration')

with open('voice_agent/templates/voice_agent/dashboard.html', 'w', encoding='utf-8') as f:
    f.write(text)
