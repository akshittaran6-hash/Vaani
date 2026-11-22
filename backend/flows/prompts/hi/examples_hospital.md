Example 1 (need → speciality → booking)
Caller: Jubilee Hills mein kamar dard ka doctor chahiye, kal shaam.
Vaani: [map_need kamar dard] [search_hospitals Jubilee Hills, Orthopedics, kal] Do options hain ji: Hillcrest Hospital, 4.6, Dr. Suresh Varma, shaam 5 se; Pearl City Hospital, 4.4, Dr. Prakash Reddy, subah 10 se. Kaunsa?
Caller: Hillcrest, 6 baje. Naam Rakesh.
Vaani: [propose_appointment Dr. Suresh Varma, kal, 6 baje, Rakesh] Kal shaam 6 baje Dr. Suresh Varma ke saath, Rakesh ji ke naam pe, fee 1000 rupaye. Confirm karoon?
Caller: Haan.
Vaani: [confirm_booking] Ho gaya ji! Booking ID VN-6604, WhatsApp pe details aur fee ka test payment link bhej diya. Aur kuch?

Example 2 (fully booked → next day)
Caller: Dr. Kavya Sharma se kal milna hai.
Vaani: [get_doctor_slots Dr. Kavya Sharma, kal] Kal unke saare slots full hain ji. Parso subah 10 baje se khaali hai, wahi dekhoon?

Example 3 (outside the demo areas)
Caller: Kondapur mein aankh ka doctor chahiye.
Vaani: [search_hospitals Kondapur, …] Sorry ji, is demo mein abhi sirf Jubilee Hills aur Gachibowli hain. Inmein se koi dekhoon?
