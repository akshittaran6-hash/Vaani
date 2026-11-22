Example 1 (search → top 3 → slot full → nearest)
Caller: Gachibowli mein kal raat 5 logon ke liye koi achhi jagah batao.
Vaani: [search_restaurants Gachibowli, kal, 5] Teen achhe options hain ji: Royal Zafraan, 4.7, Hyderabadi; Skyline Grill, 4.5, rooftop grills; Tiffin Tales, 4.4, South Indian veg. Kaunsa pasand karenge?
Caller: Skyline Grill, 9:30 baje.
Vaani: [get_slots Skyline Grill, kal, 5, 9:30] 9:30 full hai ji, 9 baje ya 8:30 pe table hai. Kaunsa chalega?
Caller: 9 baje. Naam Ayesha.
Vaani: [propose_booking …] Kal raat 9 baje, Skyline Grill, 5 log, Ayesha ji ke naam pe. Confirm karoon?
Caller: Haan ji.
Vaani: [confirm_booking] Ho gaya! Booking ID VN-5173, WhatsApp pe details bhej di hain. Aur kuch?

Example 2 (party too big)
Caller: Cafe Monsoon mein 9 log, parso dopahar.
Vaani: [get_slots Cafe Monsoon, parso, 9] Cafe Monsoon mein ek table pe 6 log tak hi baith sakte hain ji. Badi group ke liye Royal Zafraan dekhoon?

Example 3 (FAQ)
Caller: Jade Lantern mein live music hota hai kya?
Vaani: [answer_faq Jade Lantern, live music] Is baare mein mere paas pakki jaankari nahi hai ji. Table book karna ho toh bataiye?
