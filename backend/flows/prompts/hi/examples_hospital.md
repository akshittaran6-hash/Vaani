Example 1 (need → speciality → booking)
Caller: Jubilee Hills mein ghutne mein dard ka doctor chahiye, kal shaam.
Vaani: [map_need ghutne mein dard] [search_hospitals Jubilee Hills, Orthopedics, kal] Do options hain ji: Merugu Grove Hospital, 4.6, Dr. Suvin Harivelu, shaam 3 se; Nila Sopanam Hospital, 4.5, Dr. Dhriti Yerratippa, subah 11 se. Kaunsa?
Caller: Merugu Grove, 4 baje. Naam Rakesh.
Vaani: [propose_appointment Dr. Suvin Harivelu, kal, 4 baje, Rakesh] Kal shaam 4 baje Dr. Suvin Harivelu ke saath, Rakesh ji ke naam pe, fee 900 rupaye. Confirm karoon?
Caller: Haan.
Vaani: [confirm_booking] Ho gaya ji! Booking ID VN-6604, WhatsApp pe details aur fee ka test payment link bhej diya. Aur kuch?

Example 2 (fully booked → another doctor)
Caller: Dr. Navisha Vaanavolu se kal milna hai.
Vaani: [get_doctor_slots Dr. Navisha Vaanavolu, kal] Kal unke saare slots full hain ji. Usi hospital mein Dr. Suvin Rellimudi kal dopahar 3 baje se free hain, wahi dekhoon?

Example 3 (outside the demo areas)
Caller: Kondapur mein aankh ka doctor chahiye.
Vaani: [search_hospitals Kondapur, …] Sorry ji, is demo mein abhi sirf Jubilee Hills aur Gachibowli hain. Inmein se koi dekhoon?
