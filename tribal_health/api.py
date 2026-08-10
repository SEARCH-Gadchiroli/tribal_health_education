import frappe
from frappe import _
import json
import os
import requests
from frappe.utils.file_manager import save_file
from referral.api import resolve_village, transliterate_to_roman, translate_to_english

def download_kobo_attachment(attachments, question_xpath, parent_doctype, parent_docname, expected_filename=None):
    """
    Downloads a KoboToolbox media attachment and saves it into Frappe's file manager.
    Supports authorization tokens via site_config (kobo_token), fallback URLs, and filename matching.
    """
    kobo_token = frappe.conf.get("kobo_token") or frappe.conf.get("kobo_api_token")
    headers = {}
    if kobo_token:
        headers["Authorization"] = f"Token {kobo_token}"

    for att in attachments:
        xpath = att.get("question_xpath") or ""
        media_basename = att.get("media_file_basename") or ""
        att_filename = att.get("filename") or ""

        # Match either question_xpath or expected filename
        xpath_matched = (
            xpath == question_xpath
            or xpath.endswith("/" + question_xpath)
            or xpath.split("/")[-1] == question_xpath.split("/")[-1]
        )
        filename_matched = False
        if expected_filename:
            exp = str(expected_filename).strip()
            filename_matched = exp and (exp in media_basename or exp in att_filename or media_basename in exp)

        if xpath_matched or filename_matched:
            filename = media_basename or att_filename or "photo.jpg"
            urls_to_try = [
                att.get("download_url"),
                att.get("download_large_url"),
                att.get("download_medium_url"),
                att.get("download_small_url")
            ]
            for download_url in urls_to_try:
                if not download_url:
                    continue
                try:
                    frappe.logger("tribal_health").info(f"Downloading Kobo attachment from: {download_url}")
                    r = requests.get(download_url, headers=headers, timeout=30)
                    if r.status_code == 200 and r.content:
                        file_doc = save_file(
                            fname=filename,
                            content=r.content,
                            dt=parent_doctype,
                            dn=parent_docname,
                            folder="Home/Attachments",
                            is_private=0
                        )
                        return file_doc.file_url
                    else:
                        frappe.logger("tribal_health").error(
                            f"Failed to download attachment from {download_url}, status code: {r.status_code}"
                        )
                except Exception as e:
                    frappe.logger("tribal_health").error(f"Error downloading attachment {download_url}: {e}")
    return None

@frappe.whitelist(allow_guest=True)
def kobo_webhook(**kwargs):
    """
    Webhook endpoint to receive POST requests from KoboToolbox REST Services.
    Processes the raw payload, saves it to Raw Village Health Education, downloads attachments,
    transliterates/translates Marathi values to English, and creates an organized Village Health Education record.
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

        # Map Kobo's auto-generated XML tags to Raw Village Health Education fields
        doc_fields = {
            "doctype": "Raw Village Health Education",
            "date": get_kobo_val("Date") or get_kobo_val("date"),
            "select_vhe_topics": get_kobo_val("subject1"),
            "area": get_kobo_val("area"),
            "villages_in_karwafa_area": get_kobo_val("karwafa"),
            "villages_in_pendhari_area": get_kobo_val("pendhari"),
            "villages_in_dhanora_area": get_kobo_val("__004"),
            "villages_in_rangi_area": get_kobo_val("__005"),
            "villages_in_murumgao_area": get_kobo_val("__006"),
            "was_village_health_education_session_conducted_": get_kobo_val("health_edu"),
            "reason_for_not_conducting_session": get_kobo_val("__007"),
            "in_how_many_places_was_village_health_education_conducted_": get_kobo_val("_") or get_kobo_val("in_how_many_places_was_village_health_education_conducted_") or 0,
            
            "location_1_name": get_kobo_val("__010"),
            "location_1_number_of_participants": get_kobo_val("__011") or 0,
            
            "location_2_name": get_kobo_val("__013"),
            "location_2_number_of_participants": get_kobo_val("__014") or 0,
            
            "location_3_name": get_kobo_val("__016"),
            "location_3_number_of_participants": get_kobo_val("__017") or 0,
            
            "location_4_name": get_kobo_val("__019"),
            "location_4_number_of_participants": get_kobo_val("__020") or 0,
            
            "total_number_of_participants": get_kobo_val("__022") or 0,
            
            # New Raw Fields
            "gps_location": get_kobo_val("_GPS"),
            "village_patil_met": get_kobo_val("__002"),
            "village_patil_name": get_kobo_val("__024"),
            "village_patil_feedback": get_kobo_val("__025"),
            "reason_for_not_meeting_patil": get_kobo_val("__003"),
            "search_driver_name": get_kobo_val("__026"),
            "health_educator_name": get_kobo_val("__027"),
        }

        # --- TRANSLATION LOGIC FOR RAW DOCTYPE ---
        try:
            mapping_path = frappe.get_app_path('tribal_health', 'public', 'kobo_mapping.json')
            with open(mapping_path, 'r') as mf:
                kobo_map = json.load(mf)
                
            # Bridge our raw fields to the Kobo XML tags that govern them
            translation_bridge = {
                "select_vhe_topics": "subject1",
                "area": "area",
                "villages_in_karwafa_area": "karwafa",
                "villages_in_pendhari_area": "pendhari",
                "villages_in_dhanora_area": "__004",
                "villages_in_rangi_area": "__005",
                "villages_in_murumgao_area": "__006",
                "was_village_health_education_session_conducted_": "health_edu",
                "village_patil_met": "__002"
            }
            
            for frappe_field, kobo_tag in translation_bridge.items():
                raw_val = doc_fields.get(frappe_field)
                if raw_val and kobo_tag in kobo_map:
                    val_map = kobo_map[kobo_tag]
                    # Handle space separated multi-select option codes or single values
                    keys = str(raw_val).split()
                    translated = [val_map.get(k, k) for k in keys]
                    doc_fields[frappe_field] = ", ".join(translated)
        except Exception as e:
            frappe.logger("tribal_health").error(f"Raw Translation Error: {e}")
        # ----------------------------------------

        # Clean integer casting
        for field in ["in_how_many_places_was_village_health_education_conducted_", "location_1_number_of_participants", 
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

        # Insert Raw Village Health Education document
        new_raw_doc = frappe.get_doc(doc_fields)
        new_raw_doc.insert(ignore_permissions=True)

        # Download attachments and update raw document
        attachments = data.get("_attachments") or []
        photo_urls = {}
        if attachments:
            for loc_idx, key in [(1, "__012"), (2, "__015"), (3, "__018"), (4, "__021")]:
                raw_filename_val = get_kobo_val(key)
                url = download_kobo_attachment(
                    attachments, key, "Raw Village Health Education", new_raw_doc.name, expected_filename=raw_filename_val
                )
                if url:
                    photo_urls[loc_idx] = url
                    new_raw_doc.set(f"location_{loc_idx}_photo", url)
            new_raw_doc.save(ignore_permissions=True)

        # --- ORGANIZE AND MAP TO HEALTH EDUCATION ---
        # 1. Resolve Village
        raw_village = ""
        for f in ["villages_in_karwafa_area", "villages_in_pendhari_area", "villages_in_dhanora_area", "villages_in_rangi_area", "villages_in_murumgao_area"]:
            val = new_raw_doc.get(f)
            if val:
                # Value is already comma-separated or single Marathi village name from Translation Logic
                raw_village = val.split(",")[0].strip()
                break

        resolved_village = resolve_village(raw_village) if raw_village else None

        # 2. Map Area to English
        AREA_MAP = {
            "कारवाफा": "Karwafa",
            "पेंढरी": "Pendhari",
            "धानोरा": "Dhanora",
            "रांगी": "Rangi",
            "मुरूमगाव": "Murumgao",
            "1": "Karwafa",
            "2": "Pendhari",
            "3": "Dhanora",
            "4": "Rangi",
            "5": "Murumgao"
        }
        area_en = AREA_MAP.get(new_raw_doc.area) or transliterate_to_roman(new_raw_doc.area)

        # 3. Session Conducted Select (Yes/No)
        session_conducted = "Yes" if "हो" in (new_raw_doc.was_village_health_education_session_conducted_ or "") or new_raw_doc.was_village_health_education_session_conducted_ == "1" else "No"

        # 4. Reason for not conducting
        reason_not_conducted = translate_to_english(new_raw_doc.reason_for_not_conducting_session)

        # 5. GPS Parsing
        latitude, longitude = None, None
        gps_str = new_raw_doc.gps_location or ""
        gps_parts = gps_str.split()
        if len(gps_parts) >= 2:
            try:
                latitude = float(gps_parts[0])
                longitude = float(gps_parts[1])
            except ValueError:
                pass

        # 6. Village Patil
        patil_met = "Yes" if "हो" in (new_raw_doc.village_patil_met or "") or new_raw_doc.village_patil_met == "1" else "No"
        patil_name = transliterate_to_roman(new_raw_doc.village_patil_name)
        patil_feedback = translate_to_english(new_raw_doc.village_patil_feedback)
        reason_no_patil = translate_to_english(new_raw_doc.reason_for_not_meeting_patil)

        # 7. Driver & Educator Names
        driver_name = transliterate_to_roman(new_raw_doc.search_driver_name)
        educator_name = transliterate_to_roman(new_raw_doc.health_educator_name)

        # 8. Map Topics child table
        TOPICS_MAP_EN = {
            "मच्‍छरदाणीचा वापर": "Mosquito Net Usage",
            "खरूज": "Scabies",
            "पाठ कंबरदुखी": "Back Pain / LUMBAGO",
            "उष्‍माघात": "Heat Stroke",
            "पाण्‍याचे शुध्‍दीकरण": "Water Purification",
            "गजकर्ण": "Ringworm",
            "हगवण": "Diarrhea",
            "बीपी": "BP",
            "लकवा": "Paralysis",
            "जयपुर फुट कॅम्प": "Jaipur Foot Camp"
        }
        topics_list = []
        raw_topics_str = new_raw_doc.select_vhe_topics or ""
        for item in raw_topics_str.split(","):
            t_marathi = item.strip()
            if t_marathi:
                t_english = TOPICS_MAP_EN.get(t_marathi) or translate_to_english(t_marathi)
                topics_list.append({"topic": t_english})

        # 9. Map Locations child table
        locations_list = []
        for i in range(1, 5):
            name_val = new_raw_doc.get(f"location_{i}_name")
            parts_val = new_raw_doc.get(f"location_{i}_number_of_participants")
            photo_url = photo_urls.get(i)
            
            if name_val or parts_val or photo_url:
                locations_list.append({
                    "location_name": transliterate_to_roman(name_val) if name_val else "",
                    "number_of_participants": parts_val or 0,
                    "photo": photo_url or ""
                })

        # Create Organized Village Health Education
        org_doc = frappe.get_doc({
            "doctype": "Village Health Education",
            "date": new_raw_doc.date,
            "village": resolved_village,
            "area": area_en,
            "session_conducted": session_conducted,
            "reason_for_not_conducting": reason_not_conducted,
            "number_of_places": new_raw_doc.in_how_many_places_was_village_health_education_conducted_,
            "total_number_of_participants": new_raw_doc.total_number_of_participants,
            "latitude": latitude,
            "longitude": longitude,
            "gps_raw": new_raw_doc.gps_location,
            "village_patil_met": patil_met,
            "village_patil_name": patil_name,
            "village_patil_feedback": patil_feedback,
            "reason_for_not_meeting_patil": reason_no_patil,
            "search_driver_name": driver_name,
            "health_educator_name": educator_name,
            "raw_village_health_education": new_raw_doc.name,
            "topics": topics_list,
            "locations": locations_list
        })
        org_doc.insert(ignore_permissions=True)
        frappe.db.commit()

        frappe.logger("tribal_health").info(f"Processed Kobo webhook. Raw: {new_raw_doc.name}, Organized: {org_doc.name}")
        return {"status": "success", "raw_doc": new_raw_doc.name, "organized_doc": org_doc.name}

    except Exception as e:
        frappe.logger("tribal_health").error(f"Kobo Webhook Error: {frappe.get_traceback()}")
        frappe.db.rollback()
        return {"status": "error", "message": str(e)}
