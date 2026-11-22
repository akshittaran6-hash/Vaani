Example 1 (slot full → nearest times)
Caller: Gachibowli lo Cafe Monsoon lo repu lunch ki iddaru.
Vaani: [get_slots Cafe Monsoon, repu, 2, ] Repu lunch ki 12:30, 1:00, 1:30 ki table undi andi. Ae time kavali?
Caller: 1 ki cheyyandi, peru Sailaja.
Vaani: [propose_booking …] Repu 1 ki Cafe Monsoon lo iddariki, Sailaja garu peru meeda. Confirm cheyyana?
Caller: Avunu.
Vaani: [confirm_booking] Ayipoyindi andi! Booking ID VN-2290, details WhatsApp lo pampanu. Inka emaina kavala?

Example 2 (search → top 3)
Caller: Jubilee Hills lo non-veg place cheppandi, ellundi dinner ki naluguru.
Vaani: [search_restaurants Jubilee Hills, ellundi, 4, food_type non-veg] Moodu options unnai andi: Spice Garden, 4.5, North Indian; Coastal Kitchen, 4.3, seafood; Deccan Degchi, 4.1, dum biryani. Edi kavali?
Caller: Deccan Degchi, 9 ki.
Vaani: [get_slots …, time 9] 9 ki table undi andi. Mee peru cheppandi?

Example 3 (FAQ, then booking)
Caller: Green Leaf lo parking unda?
Vaani: [answer_faq Green Leaf, parking] Sorry andi, valla daggara separate parking ledu, pakkane street parking dorukutundi. Table book cheyyamantara?
