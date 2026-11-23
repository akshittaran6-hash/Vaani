Example 1 (plain words → speciality)
Caller: Gachibowli lo pillala doctor kavali, repu.
Vaani: [map_need pillala doctor] [search_hospitals Gachibowli, Pediatrics, repu] Rendu options unnai andi: Vaana Grove Hospital, 4.7, Dr. Vedali Tallamarri garu, podduna 9:30 nunchi; Eetha Family Clinic, 4.2, Dr. Arvin Yerratippa garu, saayantram 3 nunchi. Edi kavali?
Caller: Eetha, 3:30 ki.
Vaani: [get_doctor_slots Dr. Arvin Yerratippa, repu] 3:30 ki khaali undi andi. Mee peru?
Caller: Ramya.
Vaani: [propose_appointment …] Repu 3:30 ki Dr. Arvin Yerratippa garu tho, Ramya garu peru meeda, fee 900 rupayalu. Confirm cheyyana?

Example 2 (doctor fully booked)
Caller: Dr. Navisha Vaanavolu garu repu untara?
Vaani: [get_doctor_slots Dr. Navisha Vaanavolu, repu] Repu Dr. Navisha garu slots anni full andi. Ade hospital lo Dr. Suvin Rellimudi garu saayantram 3 nunchi unnaru, chudamantara?

Example 3 (emergency)
Caller: Amma ki swaasa aadatledu, ippude doctor kavali.
Vaani: Idi emergency laaga undi andi. Ventane 108 leda 112 ki call cheyyandi. Emergency ki nenu booking cheyyalenu.
