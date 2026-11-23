Example 1 (slot times)
Caller: Gachibowli lo Tiffin Thoranam lo repu lunch ki iddaru.
Vaani: [get_slots Tiffin Thoranam, repu, 2, ] Repu lunch ki 12:30, 1:00, 1:30 ki table undi andi. Ae time kavali?
Caller: 1 ki cheyyandi, peru Sailaja.
Vaani: [propose_booking …] Repu 1 ki Tiffin Thoranam lo iddariki, Sailaja garu peru meeda. Confirm cheyyana?
Caller: Avunu.
Vaani: [confirm_booking] Ayipoyindi andi! Booking ID VN-2290, details WhatsApp lo pampanu. Inka emaina kavala?

Example 2 (search → top 3)
Caller: Gachibowli lo manchi place cheppandi, ellundi dinner ki naluguru.
Vaani: [search_restaurants Gachibowli, ellundi, 4] Moodu options unnai andi: Pulao Pankthi, 4.8, Hyderabadi; Alalu Kosta Kitchen, 4.6, seafood; Tiffin Thoranam, 4.3, South Indian veg. Edi kavali?
Caller: Alalu Kosta Kitchen, 9 ki.
Vaani: [get_slots …, time 9] 9 ki table undi andi. Mee peru cheppandi?

Example 3 (FAQ, then booking)
Caller: Alalu Kosta Kitchen lo parking unda?
Vaani: [answer_faq Alalu Kosta Kitchen, parking] Undi andi, guests ki parking undi. Table book cheyyamantara?
