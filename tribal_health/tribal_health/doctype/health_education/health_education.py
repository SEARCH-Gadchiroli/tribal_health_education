# Copyright (c) 2026, SEARCH and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class HealthEducation(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		area: DF.Data | None
		date: DF.Date | None
		in_how_many_places_was_health_education_conducted_: DF.Int
		location_1_name: DF.Data | None
		location_1_number_of_participants: DF.Int
		location_2_name: DF.Data | None
		location_2_number_of_participants: DF.Int
		location_3_name: DF.Data | None
		location_3_number_of_participants: DF.Int
		location_4_name: DF.Data | None
		location_4_number_of_participants: DF.Int
		reason_for_not_conducting_session: DF.Data | None
		select_the_health_education_topics_you_can_choose_more_than_one: DF.Data | None
		total_number_of_participants: DF.Int
		villages_in_dhanora_area: DF.Data | None
		villages_in_karwafa_area: DF.Data | None
		villages_in_murumgao_area: DF.Data | None
		villages_in_pendhari_area: DF.Data | None
		villages_in_rangi_area: DF.Data | None
		was_health_education_session_conducted_: DF.Data | None
	# end: auto-generated types

	pass
