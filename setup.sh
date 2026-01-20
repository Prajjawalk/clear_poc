#!/bin/bash
set -e
source .env

# disconnect users from database if any
psql -d postgres -c "SELECT pg_terminate_backend(pg_stat_activity.pid) FROM pg_stat_activity WHERE pg_stat_activity.datname = '${DB_NAME}' AND pid <> pg_backend_pid();"
# drop and recreate database and user
psql -d postgres -c "DROP DATABASE IF EXISTS ${DB_NAME};"
psql -d postgres -c "DROP USER IF EXISTS ${DB_USER};"
psql -d postgres -c "CREATE USER ${DB_USER} PASSWORD '${DB_PASSWORD}';"
psql -d postgres -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};"
psql -d ${DB_NAME} -c "CREATE EXTENSION postgis;"

# give superuser to user in dev for testing purposes
if [ "$DJANGO_ENV" = "DEV" ]; then
    psql -d postgres -c "ALTER ROLE ${DB_USER} SUPERUSER;"
fi

export UV_ENV_FILE=.env # needed, otherwise env variables are not loaded for some reason

# install npm packages only in dev
if [ "$DJANGO_ENV" = "DEV" ]; then
    npm install
fi

uv run manage.py collectstatic --noinput
uv run manage.py makemigrations
uv run manage.py migrate
uv run manage.py createsuperuser --noinput --username ${DJANGO_SUPERUSER_USERNAME} --email ${DJANGO_SUPERUSER_EMAIL}
# load fixtures
fixtures=(
    # data pipeline
    "data_pipeline/fixtures/data_pipeline.source.json"
    "data_pipeline/fixtures/data_pipeline.variable.json"
    "data_pipeline/fixtures/data_pipeline.variabledata.json"
    # location
    "location/fixtures/location.admlevel.json"
    "location/fixtures/location.location.json"
    "location/fixtures/location.gazetteer.json"
    # task monitoring
    "task_monitoring/fixtures/task_monitoring.task_type.json"
    "task_monitoring/fixtures/django_celery_beat.crontabschedule.json"
    "task_monitoring/fixtures/django_celery_beat.periodictask.json"
    # translation
    "translation/fixtures/translation.translationstring.json"
    # auth
    "app/fixtures/auth_groups.json"
    "app/fixtures/auth.user.json"
    "app/fixtures/auth.user_groups.json"
    "users/fixtures/users.userprofile.json"
    # alerts
    "alerts/fixtures/alerts.shocktype.json"
    "alerts/fixtures/alerts.alert.json"
    "alerts/fixtures/alerts.alert_locations.json"
    "alerts/fixtures/alerts.subscription.json"
    "alerts/fixtures/alerts.subscription_locations.json"
    "alerts/fixtures/alerts.subscription_shock_types.json"
    "alerts/fixtures/alerts.emailtemplate.json"
    # alert framework
    "alert_framework/fixtures/alert_framework.detector.json"
    "alert_framework/fixtures/alert_framework.alerttemplate.json"
    # LLM Query Service
    "llm_service/fixtures/llm_service.providerconfig.json"

    # test integration fixtures - provides complete testing system
    # includes: test source, variables (displaced_population, resource_availability),
    # detector with predictable data generation, email templates, notifications
    "data_pipeline/fixtures/test_source.json"
    "data_pipeline/fixtures/test_variable.json"
    "alert_framework/fixtures/test_detector.json"
)

for fixture in "${fixtures[@]}"; do
    uv run python manage.py loaddata "$fixture"
done
# load compressed variabledata fixture
# gzip -dc data_pipeline/fixtures/data_pipeline.variabledata.json.gz | uv run python manage.py loaddata -

# remove raw_data
rm -rf raw_data/*

# clear any pending Celery tasks (useful after database reset)
uv run manage.py clear_celery_tasks --all --force

# Demo users are now loaded via fixtures above

# Update settlements to put them in the current admin3
sql="UPDATE location_location
  SET parent_id = (
      SELECT id FROM location_location districts
      WHERE districts.admin_level_id = 3
      AND ST_Contains(districts.boundary, location_location.point)
  )
  WHERE admin_level_id = 4;"
psql -d ${DB_NAME} -c "$sql"

# set name_ar to null when it's empty
sql="UPDATE location_location SET name_ar = NULL WHERE name_ar = '';"
psql -d ${DB_NAME} -c "$sql"

# populate location centroids and point types
echo "Populating location centroids..."
uv run manage.py populate_location_centroids
