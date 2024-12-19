from nautobot.apps.jobs import Job, TextVar, register_jobs
from nautobot.dcim.models import Location, LocationType
from nautobot.extras.models import Status
import csv
from io import StringIO

# State abbreviation mapping
STATE_MAPPING = {
    'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas', 
    'CA': 'California', 'CO': 'Colorado', 'CT': 'Connecticut', 'DE': 'Delaware',
    'FL': 'Florida', 'GA': 'Georgia', 'HI': 'Hawaii', 'ID': 'Idaho',
    'IL': 'Illinois', 'IN': 'Indiana', 'IA': 'Iowa', 'KS': 'Kansas',
    'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine', 'MD': 'Maryland',
    'MA': 'Massachusetts', 'MI': 'Michigan', 'MN': 'Minnesota', 'MS': 'Mississippi',
    'MO': 'Missouri', 'MT': 'Montana', 'NE': 'Nebraska', 'NV': 'Nevada',
    'NH': 'New Hampshire', 'NJ': 'New Jersey', 'NM': 'New Mexico', 'NY': 'New York',
    'NC': 'North Carolina', 'ND': 'North Dakota', 'OH': 'Ohio', 'OK': 'Oklahoma',
    'OR': 'Oregon', 'PA': 'Pennsylvania', 'RI': 'Rhode Island', 'SC': 'South Carolina',
    'SD': 'South Dakota', 'TN': 'Tennessee', 'TX': 'Texas', 'UT': 'Utah',
    'VT': 'Vermont', 'VA': 'Virginia', 'WA': 'Washington', 'WV': 'West Virginia',
    'WI': 'Wisconsin', 'WY': 'Wyoming'
}

class LocationImportJob(Job):
    """Import locations with full hierarchy: State -> City -> Branch/DC."""
    
    class Meta:
        name = "Location Import"
        description = "Import locations with state and city hierarchy"
        has_sensitive_variables = False
        
    csv_data = TextVar(
        description="CSV data with headers: name,city,state",
        label="CSV Data"
    )

    def normalize_state(self, state):
        """Convert state abbreviation to full name."""
        if state in STATE_MAPPING:
            return STATE_MAPPING[state]
        return state.title()

    def get_location_type(self, name):
        """Determine location type based on name suffix."""
        if name.endswith('-DC'):
            return LocationType.objects.get(name="Data Center")
        elif name.endswith('-BR'):
            return LocationType.objects.get(name="Branch")
        else:
            raise ValueError(f"Location name {name} must end with either -DC or -BR")

    def run(self, csv_data):
        """Process the CSV data and create location hierarchy."""
        
        csv_file = StringIO(csv_data.strip())
        reader = csv.DictReader(csv_file)
        
        # Get required location types
        state_type = LocationType.objects.get(name="State")
        city_type = LocationType.objects.get(name="City")
        
        # Get active status
        active_status = Status.objects.get(name="Active")
        
        created_or_updated = []
        
        for row in reader:
            try:
                # 1. Create/Get State Location
                full_state_name = self.normalize_state(row['state'])
                state_location, state_created = Location.objects.get_or_create(
                    name=full_state_name,
                    location_type=state_type,
                    defaults={'status': active_status}
                )
                if state_created:
                    self.logger.info(f"Created state location: {full_state_name}")

                # 2. Create/Get City Location
                city_location, city_created = Location.objects.get_or_create(
                    name=row['city'],
                    location_type=city_type,
                    parent=state_location,
                    defaults={'status': active_status}
                )
                if city_created:
                    self.logger.info(f"Created city location: {row['city']} in {full_state_name}")

                # 3. Create/Update Branch or DC Location
                location_type = self.get_location_type(row['name'])
                site_location, site_created = Location.objects.get_or_create(
                    name=row['name'],
                    defaults={
                        'location_type': location_type,
                        'status': active_status,
                        'parent': city_location,
                    }
                )
                
                if not site_created:
                    # Update existing location if needed
                    site_location.location_type = location_type
                    site_location.status = active_status
                    site_location.parent = city_location
                    site_location.save()

                action = "Created" if site_created else "Updated"
                created_or_updated.append(site_location)
                self.logger.info(
                    f"{action} location: {site_location.name} in {row['city']}, {full_state_name}",
                    extra={"object": site_location}
                )
                
            except Exception as e:
                self.logger.error(
                    f"Error processing location {row.get('name', '')}: {str(e)}",
                )
                raise

        return f"Successfully processed {len(created_or_updated)} locations"

register_jobs(LocationImportJob)
