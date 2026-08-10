import frappe
from frappe import _
from frappe.utils import getdate, cint

no_cache = True

def format_to_dd_mm_yyyy(date_val):
	if not date_val:
		return ""
	try:
		return getdate(date_val).strftime("%d-%m-%Y")
	except Exception:
		return str(date_val)

def get_context(context):
	# 1. Guest Check
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/village_health_education"
		raise frappe.Redirect

	# 2. Permission Check
	user_roles = frappe.get_roles()
	has_access = (
		"System Manager" in user_roles or 
		"Tribal Health User" in user_roles or 
		frappe.has_permission("Village Health Education", "read")
	)
	if not has_access:
		frappe.throw(
			_("You do not have permission to view this page. Access is restricted to authorized users."), 
			frappe.PermissionError
		)

	# 3. Retrieve request parameters
	form_dict = frappe.form_dict
	search = form_dict.get("search", "").strip()
	area = form_dict.get("area", "").strip()
	village = form_dict.get("village", "").strip()
	session_conducted = form_dict.get("session_conducted", "").strip()
	topic = form_dict.get("topic", "").strip()
	start_date = form_dict.get("start_date", "").strip()
	end_date = form_dict.get("end_date", "").strip()
	
	# Pagination parameters
	page = cint(form_dict.get("page", 1))
	if page < 1:
		page = 1
	page_size = 20
	limit_start = (page - 1) * page_size

	# 4. Build database query conditions
	conditions = []
	values = {}

	if search:
		conditions.append(
			"(name LIKE %(search)s OR village LIKE %(search)s OR area LIKE %(search)s OR health_educator_name LIKE %(search)s)"
		)
		values["search"] = f"%{search}%"
	
	if area:
		conditions.append("area = %(area)s")
		values["area"] = area
		
	if village:
		conditions.append("village = %(village)s")
		values["village"] = village
		
	if session_conducted:
		conditions.append("session_conducted = %(session_conducted)s")
		values["session_conducted"] = session_conducted
		
	if start_date:
		conditions.append("date >= %(start_date)s")
		values["start_date"] = start_date
		
	if end_date:
		conditions.append("date <= %(end_date)s")
		values["end_date"] = end_date

	if topic:
		conditions.append(
			"EXISTS (SELECT 1 FROM `tabVillage Health Education Topic` t WHERE t.parent = `tabVillage Health Education`.name AND t.topic = %(topic)s)"
		)
		values["topic"] = topic

	where_clause = " AND ".join(conditions) if conditions else "1=1"

	# Get total record count for pagination
	total_records = frappe.db.sql(f"""
		SELECT COUNT(*) FROM `tabVillage Health Education` WHERE {where_clause}
	""", values)[0][0]
	total_pages = (total_records + page_size - 1) // page_size

	# Get paginated health education records
	records = frappe.db.sql(f"""
		SELECT 
			name, date, village, area, session_conducted, reason_for_not_conducting,
			number_of_places, total_number_of_participants, latitude, longitude, gps_raw,
			village_patil_met, village_patil_name, village_patil_feedback, reason_for_not_meeting_patil,
			search_driver_name, health_educator_name, raw_village_health_education, creation
		FROM `tabVillage Health Education`
		WHERE {where_clause}
		ORDER BY date DESC, creation DESC
		LIMIT {limit_start}, {page_size}
	""", values, as_dict=True)

	# Format dates and retrieve child table elements
	for rec in records:
		if rec.get("date"):
			rec["formatted_date"] = format_to_dd_mm_yyyy(rec["date"])
			rec["date"] = str(rec["date"])
		else:
			rec["formatted_date"] = ""
			rec["date"] = ""
			
		if rec.get("creation"):
			rec["creation"] = str(rec["creation"])

		# Retrieve Topics child table
		rec["topics"] = frappe.db.get_values(
			"Village Health Education Topic",
			{"parent": rec["name"], "parenttype": "Village Health Education"},
			["topic"],
			as_dict=True,
			order_by="idx asc"
		) or []

		# Retrieve Locations child table
		rec["locations"] = frappe.db.get_values(
			"Village Health Education Location",
			{"parent": rec["name"], "parenttype": "Village Health Education"},
			["location_name", "number_of_participants", "photo"],
			as_dict=True,
			order_by="idx asc"
		) or []

	# 5. Populate filters lists dynamically
	filter_areas = [r[0] for r in frappe.db.sql("""
		SELECT DISTINCT area FROM `tabVillage Health Education` 
		WHERE area IS NOT NULL AND area != '' 
		ORDER BY area ASC
	""")]

	filter_villages = [r[0] for r in frappe.db.sql("""
		SELECT DISTINCT village FROM `tabVillage Health Education` 
		WHERE village IS NOT NULL AND village != '' 
		ORDER BY village ASC
	""")]

	filter_topics = [r[0] for r in frappe.db.sql("""
		SELECT DISTINCT topic FROM `tabVillage Health Education Topic` 
		WHERE topic IS NOT NULL AND topic != '' 
		ORDER BY topic ASC
	""")]

	# User greeting / fullname
	user_fullname = frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user

	# Update context dictionary for the HTML template
	context.update({
		"title": _("Village Health Education Sessions — SEARCH"),
		"user_fullname": user_fullname,
		"records": records,
		"records_json": frappe.as_json(records),
		"total_records": total_records,
		"total_pages": total_pages,
		"current_page": page,
		"filters": {
			"search": search,
			"area": area,
			"village": village,
			"session_conducted": session_conducted,
			"topic": topic,
			"start_date": start_date,
			"end_date": end_date,
		},
		"filter_areas": filter_areas,
		"filter_villages": filter_villages,
		"filter_topics": filter_topics,
	})

	return context
