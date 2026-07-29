from django.core.management.base import BaseCommand
from apps.core.reference.models import Country, Nationality, Language, Currency, DocumentType, ReservationSource, Timezone, State

class Command(BaseCommand):
    help = 'Seeds Global Reference Data including ISO countries, currencies, languages, nationalities, document types, reservation sources, and timezones.'

    def handle(self, *args, **kwargs):
        self.stdout.write("Seeding global reference data...")

        # 1. ISO Currencies
        currencies = [
            {"code": "USD", "name": "US Dollar", "symbol": "$"},
            {"code": "INR", "name": "Indian Rupee", "symbol": "₹"},
            {"code": "EUR", "name": "Euro", "symbol": "€"},
            {"code": "GBP", "name": "British Pound", "symbol": "£"},
            {"code": "CAD", "name": "Canadian Dollar", "symbol": "C$"},
            {"code": "AUD", "name": "Australian Dollar", "symbol": "A$"},
            {"code": "JPY", "name": "Japanese Yen", "symbol": "¥"},
            {"code": "AED", "name": "UAE Dirham", "symbol": "د.إ"},
            {"code": "SGD", "name": "Singapore Dollar", "symbol": "S$"},
            {"code": "CHF", "name": "Swiss Franc", "symbol": "CHF"},
            {"code": "CNY", "name": "Chinese Yuan", "symbol": "¥"},
            {"code": "NZD", "name": "New Zealand Dollar", "symbol": "NZ$"},
        ]
        for curr in currencies:
            Currency.objects.update_or_create(code=curr["code"], defaults=curr)
        self.stdout.write(self.style.SUCCESS(f"Successfully seeded {len(currencies)} currencies."))

        # 2. ISO Countries
        countries = [
            {"code": "US", "name": "United States", "phone_code": "+1"},
            {"code": "IN", "name": "India", "phone_code": "+91"},
            {"code": "GB", "name": "United Kingdom", "phone_code": "+44"},
            {"code": "CA", "name": "Canada", "phone_code": "+1"},
            {"code": "DE", "name": "Germany", "phone_code": "+49"},
            {"code": "FR", "name": "France", "phone_code": "+33"},
            {"code": "AU", "name": "Australia", "phone_code": "+61"},
            {"code": "JP", "name": "Japan", "phone_code": "+81"},
            {"code": "AE", "name": "United Arab Emirates", "phone_code": "+971"},
            {"code": "SG", "name": "Singapore", "phone_code": "+65"},
            {"code": "CH", "name": "Switzerland", "phone_code": "+41"},
            {"code": "CN", "name": "China", "phone_code": "+86"},
            {"code": "NZ", "name": "New Zealand", "phone_code": "+64"},
        ]
        for country in countries:
            Country.objects.update_or_create(code=country["code"], defaults=country)
        self.stdout.write(self.style.SUCCESS(f"Successfully seeded {len(countries)} countries."))

        # 3. Common Languages
        languages = [
            {"code": "en", "name": "English"},
            {"code": "es", "name": "Spanish"},
            {"code": "fr", "name": "French"},
            {"code": "de", "name": "German"},
            {"code": "hi", "name": "Hindi"},
            {"code": "zh", "name": "Chinese"},
            {"code": "ja", "name": "Japanese"},
            {"code": "ar", "name": "Arabic"},
            {"code": "pt", "name": "Portuguese"},
            {"code": "it", "name": "Italian"},
            {"code": "ru", "name": "Russian"},
        ]
        for lang in languages:
            Language.objects.update_or_create(code=lang["code"], defaults=lang)
        self.stdout.write(self.style.SUCCESS(f"Successfully seeded {len(languages)} languages."))

        # 4. Nationalities
        nationalities = [
            {"code": "american", "name": "American"},
            {"code": "indian", "name": "Indian"},
            {"code": "british", "name": "British"},
            {"code": "canadian", "name": "Canadian"},
            {"code": "german", "name": "German"},
            {"code": "french", "name": "French"},
            {"code": "australian", "name": "Australian"},
            {"code": "japanese", "name": "Japanese"},
            {"code": "emirati", "name": "Emirati"},
            {"code": "singaporean", "name": "Singaporean"},
            {"code": "swiss", "name": "Swiss"},
            {"code": "chinese", "name": "Chinese"},
            {"code": "kiwi", "name": "New Zealander"},
        ]
        for nat in nationalities:
            Nationality.objects.update_or_create(code=nat["code"], defaults=nat)
        self.stdout.write(self.style.SUCCESS(f"Successfully seeded {len(nationalities)} nationalities."))

        # 5. Global Document Types
        doc_types = [
            {"code": "passport", "name": "Passport"},
            {"code": "national_id", "name": "National ID Card"},
            {"code": "driving_license", "name": "Driving License"},
            {"code": "visa", "name": "Visa"},
            {"code": "voter_id", "name": "Voter ID Card"},
            {"code": "pan_card", "name": "PAN Card"},
        ]
        for doc in doc_types:
            DocumentType.objects.update_or_create(code=doc["code"], defaults=doc)
        self.stdout.write(self.style.SUCCESS(f"Successfully seeded {len(doc_types)} document types."))

        # 6. Common Reservation Sources
        sources = [
            {"code": "direct", "name": "Direct / Walk-In"},
            {"code": "website", "name": "Brand Website"},
            {"code": "booking_com", "name": "Booking.com"},
            {"code": "expedia", "name": "Expedia"},
            {"code": "agoda", "name": "Agoda"},
            {"code": "airbnb", "name": "Airbnb"},
            {"code": "corporate", "name": "Corporate Client"},
            {"code": "travel_agent", "name": "Offline Travel Agent"},
            {"code": "email_phone", "name": "Email / Phone Inquiry"},
        ]
        for src in sources:
            ReservationSource.objects.update_or_create(code=src["code"], defaults=src)
        self.stdout.write(self.style.SUCCESS(f"Successfully seeded {len(sources)} reservation sources."))

        # 7. Timezones
        timezones = [
            {"code": "UTC", "name": "UTC (Coordinated Universal Time)", "utc_offset": "+00:00"},
            {"code": "America/New_York", "name": "Eastern Time (New York)", "utc_offset": "-05:00"},
            {"code": "America/Chicago", "name": "Central Time (Chicago)", "utc_offset": "-06:00"},
            {"code": "America/Denver", "name": "Mountain Time (Denver)", "utc_offset": "-07:00"},
            {"code": "America/Los_Angeles", "name": "Pacific Time (Los Angeles)", "utc_offset": "-08:00"},
            {"code": "Europe/London", "name": "Greenwich Mean Time (London)", "utc_offset": "+00:00"},
            {"code": "Europe/Paris", "name": "Central European Time (Paris)", "utc_offset": "+01:00"},
            {"code": "Asia/Kolkata", "name": "India Standard Time (Kolkata)", "utc_offset": "+05:30"},
            {"code": "Asia/Singapore", "name": "Singapore Time", "utc_offset": "+08:00"},
            {"code": "Asia/Tokyo", "name": "Japan Standard Time (Tokyo)", "utc_offset": "+09:00"},
            {"code": "Australia/Sydney", "name": "Eastern Time (Sydney)", "utc_offset": "+10:00"},
            {"code": "Pacific/Auckland", "name": "New Zealand Time (Auckland)", "utc_offset": "+12:00"},
        ]
        for tz in timezones:
            Timezone.objects.update_or_create(code=tz["code"], defaults=tz)
        self.stdout.write(self.style.SUCCESS(f"Successfully seeded {len(timezones)} timezones."))

        # 8. States/Provinces for countries
        states_data = {
            "IN": [
                {"code": "DL", "name": "Delhi"},
                {"code": "MH", "name": "Maharashtra"},
                {"code": "KA", "name": "Karnataka"},
                {"code": "TN", "name": "Tamil Nadu"},
                {"code": "UP", "name": "Uttar Pradesh"},
                {"code": "WB", "name": "West Bengal"},
                {"code": "GJ", "name": "Gujarat"},
                {"code": "TS", "name": "Telangana"},
                {"code": "KL", "name": "Kerala"},
                {"code": "OD", "name": "Odisha"},
            ],
            "US": [
                {"code": "CA", "name": "California"},
                {"code": "TX", "name": "Texas"},
                {"code": "NY", "name": "New York"},
                {"code": "FL", "name": "Florida"},
                {"code": "IL", "name": "Illinois"},
                {"code": "WA", "name": "Washington"},
                {"code": "MA", "name": "Massachusetts"},
                {"code": "CO", "name": "Colorado"},
            ],
            "GB": [
                {"code": "ENG", "name": "England"},
                {"code": "SCT", "name": "Scotland"},
                {"code": "WLS", "name": "Wales"},
                {"code": "NIR", "name": "Northern Ireland"},
            ],
            "CA": [
                {"code": "ON", "name": "Ontario"},
                {"code": "QC", "name": "Quebec"},
                {"code": "BC", "name": "British Columbia"},
                {"code": "AB", "name": "Alberta"},
            ],
            "AU": [
                {"code": "NSW", "name": "New South Wales"},
                {"code": "VIC", "name": "Victoria"},
                {"code": "QLD", "name": "Queensland"},
                {"code": "WA", "name": "Western Australia"},
            ]
        }

        state_count = 0
        for country_code, states in states_data.items():
            try:
                country_obj = Country.objects.get(code=country_code)
                for st in states:
                    State.objects.update_or_create(
                        country=country_obj,
                        code=st["code"],
                        defaults={"name": st["name"]}
                    )
                    state_count += 1
            except Country.DoesNotExist:
                pass
        self.stdout.write(self.style.SUCCESS(f"Successfully seeded {state_count} states."))

        # 8. Seed RBAC Permissions & Roles
        try:
            from django.core.management import call_command
            call_command('seed_rbac_permissions')
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"RBAC seeding warning: {e}"))

        self.stdout.write(self.style.SUCCESS("Global reference data seeding completed!"))

