import frappe
from frappe import _
import json
import os

@frappe.whitelist(allow_guest=True)
def kobo_webhook(**kwargs):
    """
    Webhook endpoint to receive POST requests from KoboToolbox REST Services.
    """
    try:
        payload = frappe.request.get_data()
        if not payload:
            return {"status": "error", "message": "Empty payload"}
            
        data = json.loads(payload)
        
        # DEBUG: Save last payload locally so we can inspect the exact structure later if needed
        try:
            log_path = os.path.join(frappe.get_site_path(), "public", "kobo_last_payload.json")
            with open(log_path, "w") as f:
                json.dump(data, f, indent=4)
        except Exception:
            pass

        # Helper to recursively find a key or suffix in Kobo's nested/slashed JSON
        def get_kobo_val(target_key):
            if target_key in data:
                return data[target_key]
            for k, v in data.items():
                if str(k).endswith(f"/{target_key}") or str(k) == target_key:
                    return v
            return ""

        # Map Kobo's auto-generated XML tags to our descriptive DocType fields
        doc_fields = {
            "doctype": "Health Education",
            "date": get_kobo_val("Date") or get_kobo_val("date"),
            "select_the_health_education_topics_you_can_choose_more_than_one": get_kobo_val("subject1"),
            "area": get_kobo_val("area"),
            "villages_in_karwafa_area": get_kobo_val("karwafa"),
            "villages_in_pendhari_area": get_kobo_val("pendhari"),
            "villages_in_dhanora_area": get_kobo_val("__004"),
            "villages_in_rangi_area": get_kobo_val("__005"),
            "villages_in_murumgao_area": get_kobo_val("__006"),
            "was_health_education_session_conducted_": get_kobo_val("health_edu"),
            "reason_for_not_conducting_session": get_kobo_val("__007"),
            "in_how_many_places_was_health_education_conducted_": get_kobo_val("_") or get_kobo_val("in_how_many_places_was_health_education_conducted_") or 0,
            
            "location_1_name": get_kobo_val("__010"),
            "location_1_number_of_participants": get_kobo_val("__011") or 0,
            
            "location_2_name": get_kobo_val("__013"),
            "location_2_number_of_participants": get_kobo_val("__014") or 0,
            
            "location_3_name": get_kobo_val("__016"),
            "location_3_number_of_participants": get_kobo_val("__017") or 0,
            
            "location_4_name": get_kobo_val("__019"),
            "location_4_number_of_participants": get_kobo_val("__020") or 0,
            
            "total_number_of_participants": get_kobo_val("__022") or 0
        }

        # --- TRANSLATION LOGIC ---
        try:
            mapping_path = frappe.get_app_path('tribal_health', 'public', 'kobo_mapping.json')
            with open(mapping_path, 'r') as mf:
                kobo_map = json.load(mf)
                
            # Bridge our clean DocType fieldnames to the Kobo XML tags that govern them
            translation_bridge = {
                "select_the_health_education_topics_you_can_choose_more_than_one": "subject1",
                "area": "area",
                "villages_in_karwafa_area": "karwafa",
                "villages_in_pendhari_area": "pendhari",
                "villages_in_dhanora_area": "__004",
                "villages_in_rangi_area": "__005",
                "villages_in_murumgao_area": "__006",
                "was_health_education_session_conducted_": "health_edu"
            }
            
            for frappe_field, kobo_tag in translation_bridge.items():
                raw_val = doc_fields.get(frappe_field)
                if raw_val and kobo_tag in kobo_map:
                    val_map = kobo_map[kobo_tag]
                    # Handle multi-select space separated strings (e.g., "1 3 4") 
                    # and single selects identically
                    keys = str(raw_val).split()
                    translated = [val_map.get(k, k) for k in keys]
                    doc_fields[frappe_field] = ", ".join(translated)
        except Exception as e:
            frappe.logger("tribal_health").error(f"Translation Error: {e}")
        # ------------------------

        # Clean integer casting
        for field in ["in_how_many_places_was_health_education_conducted_", "location_1_number_of_participants", 
                      "location_2_number_of_participants", "location_3_number_of_participants", 
                      "location_4_number_of_participants", "total_number_of_participants"]:
            try:
                doc_fields[field] = int(float(doc_fields[field])) if doc_fields[field] else 0
            except ValueError:
                doc_fields[field] = 0

        if doc_fields["total_number_of_participants"] == 0:
            doc_fields["total_number_of_participants"] = sum([
                doc_fields.get("location_1_number_of_participants", 0),
                doc_fields.get("location_2_number_of_participants", 0),
                doc_fields.get("location_3_number_of_participants", 0),
                doc_fields.get("location_4_number_of_participants", 0)
            ])

        new_doc = frappe.get_doc(doc_fields)
        new_doc.insert(ignore_permissions=True)
        frappe.db.commit()

        frappe.logger("tribal_health").info(f"Successfully processed Kobo webhook. Doc: {new_doc.name}")
        return {"status": "success", "doc_name": new_doc.name}

    except Exception as e:
        frappe.logger("tribal_health").error(f"Kobo Webhook Error: {frappe.get_traceback()}")
        frappe.db.rollback()
        return {"status": "error", "message": str(e)}
