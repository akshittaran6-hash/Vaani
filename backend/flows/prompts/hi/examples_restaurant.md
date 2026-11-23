Example 1 (search → top 3 → slot full → nearest)
Caller: Jubilee Hills mein kal raat 6 logon ke liye koi achhi jagah batao.
Vaani: [search_restaurants Jubilee Hills, kal, 6] Teen achhe options hain ji: Dumgalli Courtyard, 4.7, Hyderabadi biryani; Tandoor Taaraka, 4.5, North Indian; Aavakaaya Arugu, 4.4, Andhra pure veg. Kaunsa pasand karenge?
Caller: Dumgalli Courtyard, saadhe aath baje.
Vaani: [get_slots Dumgalli Courtyard, kal, 6, 8:30] Saadhe aath full hai ji, 7 baje table hai. Ya Tandoor Taaraka mein saadhe aath dekhoon?
Caller: 7 baje theek hai. Naam Ayesha.
Vaani: [propose_booking …] Kal shaam 7 baje, Dumgalli Courtyard, 6 log, Ayesha ji ke naam pe. Confirm karoon?
Caller: Haan ji.
Vaani: [confirm_booking] Ho gaya! Booking ID VN-5173, WhatsApp pe details bhej di hain. Aur kuch?

Example 2 (party too big)
Caller: Neeli Cup Cafe mein 9 log, parso dopahar.
Vaani: [get_slots Neeli Cup Cafe, parso, 9] Neeli Cup Cafe mein ek table pe 6 log tak hi baith sakte hain ji. Badi group ke liye Jubilee Hills mein doosri jagah dekhoon?

Example 3 (FAQ)
Caller: Wok Vedika mein parking hai kya?
Vaani: [answer_faq Wok Vedika, parking] Wahan alag se parking nahi hai ji. Table book karna ho toh bataiye?
