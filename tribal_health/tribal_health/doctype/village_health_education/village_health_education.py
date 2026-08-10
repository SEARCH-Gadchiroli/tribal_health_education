# Copyright (c) 2026, SEARCH and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import getdate, today


class VillageHealthEducation(Document):
	def autoname(self):
		if self.date:
			date_str = getdate(self.date).strftime("%d%m%y")
		else:
			date_str = getdate(today()).strftime("%d%m%y")
			
		prefix = f"{date_str}-"
		
		# Retrieve existing names starting with this prefix to calculate the next sequence number robustly
		existing_names = frappe.get_all("Village Health Education", filters=[["name", "like", f"{prefix}%"]], pluck="name")
		
		max_num = 0
		for name in existing_names:
			parts = name.split("-")
			if len(parts) == 2:
				try:
					num = int(parts[1])
					if num > max_num:
						max_num = num
				except ValueError:
					pass
					
		next_num = max_num + 1
		self.name = f"{prefix}{next_num}"
