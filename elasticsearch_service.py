"""
Elasticsearch service for ultra-fast doctor search.
ES 8/9 uses HTTPS + security by default.
All methods fail silently — app falls back to PostgreSQL automatically.
"""
from typing import Optional, List, Dict, Any
from app.config import settings

_es = None

DOCTOR_INDEX = settings.ELASTICSEARCH_INDEX_DOCTORS

DOCTOR_MAPPING = {
    "mappings": {
        "properties": {
            "id":                     {"type": "integer"},
            "user_id":                {"type": "integer"},
            "full_name":              {"type": "text", "analyzer": "standard",
                                       "fields": {"keyword": {"type": "keyword"}}},
            "specialization":         {"type": "text", "analyzer": "standard",
                                       "fields": {"keyword": {"type": "keyword"}}},
            "specialization_id":      {"type": "integer"},
            "bio":                    {"type": "text", "analyzer": "standard"},
            "languages":              {"type": "keyword"},
            "city":                   {"type": "keyword"},
            "state":                  {"type": "keyword"},
            "pincode":                {"type": "keyword"},
            "clinic_name":            {"type": "text"},
            "clinic_address":         {"type": "text"},
            "consultation_fee":       {"type": "float"},
            "video_fee":              {"type": "float"},
            "experience_years":       {"type": "integer"},
            "avg_rating":             {"type": "float"},
            "total_reviews":          {"type": "integer"},
            "gender":                 {"type": "keyword"},
            "available_for_video":    {"type": "boolean"},
            "available_for_home":     {"type": "boolean"},
            "accepting_new_patients": {"type": "boolean"},
            "is_verified":            {"type": "boolean"},
            "is_featured":            {"type": "boolean"},
            "avatar_url":             {"type": "keyword"},
            "location":               {"type": "geo_point"},
        }
    },
    "settings": {"number_of_shards": 1, "number_of_replicas": 0},
}


def _make_client():
    """Create AsyncElasticsearch client with HTTPS + basic auth."""
    from elasticsearch import AsyncElasticsearch
    import ssl

    # Build a permissive SSL context that skips cert verification
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    kwargs: dict = {
        "hosts": [settings.ELASTICSEARCH_URL],
        "ssl_context": ssl_ctx,
    }
    if settings.ELASTICSEARCH_USER and settings.ELASTICSEARCH_PASSWORD:
        kwargs["basic_auth"] = (
            settings.ELASTICSEARCH_USER,
            settings.ELASTICSEARCH_PASSWORD,
        )
    return AsyncElasticsearch(**kwargs)


async def get_es():
    """Return a live ES client, or None if ES is unavailable."""
    global _es
    if _es is not None:
        return _es
    try:
        client = _make_client()
        info = await client.info()
        print(f"✅  Elasticsearch {info['version']['number']} connected")
        _es = client
    except Exception as exc:
        print(f"⚠️   Elasticsearch unavailable — using PostgreSQL fallback ({exc})")
        _es = None
    return _es


async def ensure_index():
    """Create the doctors index if it doesn't exist. Never raises."""
    try:
        es = await get_es()
        if es is None:
            return
        exists = await es.indices.exists(index=DOCTOR_INDEX)
        if not exists:
            await es.indices.create(index=DOCTOR_INDEX, body=DOCTOR_MAPPING)
            print(f"✅  Elasticsearch index '{DOCTOR_INDEX}' created")
        else:
            print(f"✅  Elasticsearch index '{DOCTOR_INDEX}' ready")
    except Exception as exc:
        print(f"⚠️   ES ensure_index failed (non-fatal): {exc}")


async def index_doctor(doctor_data: dict):
    try:
        es = await get_es()
        if not es:
            return
        doc_id = str(doctor_data["id"])
        if doctor_data.get("latitude") and doctor_data.get("longitude"):
            doctor_data["location"] = {
                "lat": doctor_data["latitude"],
                "lon": doctor_data["longitude"],
            }
        await es.index(index=DOCTOR_INDEX, id=doc_id, document=doctor_data)
    except Exception as exc:
        print(f"⚠️   ES index_doctor failed (non-fatal): {exc}")


async def delete_doctor_from_index(doctor_id: int):
    try:
        es = await get_es()
        if not es:
            return
        await es.delete(index=DOCTOR_INDEX, id=str(doctor_id))
    except Exception:
        pass


async def search_doctors(params: dict) -> Optional[Dict[str, Any]]:
    """
    Run an ES search. Returns None on any error so caller falls back to PG.
    """
    try:
        es = await get_es()
        if not es:
            return None

        must:    List[dict] = []
        filter_: List[dict] = []

        if params.get("q"):
            must.append({
                "multi_match": {
                    "query":  params["q"],
                    "fields": ["full_name^3", "specialization^2", "bio",
                               "clinic_name", "clinic_address"],
                    "type":       "best_fields",
                    "fuzziness":  "AUTO",
                }
            })

        for field, es_field in [
            ("specialization_id", "specialization_id"),
            ("city",   "city"),
            ("state",  "state"),
            ("pincode","pincode"),
            ("gender", "gender"),
        ]:
            if params.get(field):
                filter_.append({"term": {es_field: params[field]}})

        for bool_field in ["available_for_video", "available_for_home",
                           "accepting_new_patients", "is_verified"]:
            if params.get(bool_field) is not None:
                filter_.append({"term": {bool_field: params[bool_field]}})

        if params.get("language"):
            filter_.append({"term": {"languages": params["language"]}})

        fee_range: dict = {}
        if params.get("min_fee") is not None:
            fee_range["gte"] = params["min_fee"]
        if params.get("max_fee") is not None:
            fee_range["lte"] = params["max_fee"]
        if fee_range:
            filter_.append({"range": {"consultation_fee": fee_range}})

        if params.get("min_rating") is not None:
            filter_.append({"range": {"avg_rating": {"gte": params["min_rating"]}}})
        if params.get("min_experience") is not None:
            filter_.append({"range": {"experience_years": {"gte": params["min_experience"]}}})

        if params.get("lat") and params.get("lng"):
            filter_.append({
                "geo_distance": {
                    "distance": f"{params.get('radius_km', 10)}km",
                    "location": {"lat": params["lat"], "lon": params["lng"]},
                }
            })

        query = {
            "bool": {
                "must":   must if must else [{"match_all": {}}],
                "filter": filter_,
            }
        }

        sort_map = {
            "relevance":  ["_score", {"is_featured": "desc"}, {"avg_rating": "desc"}],
            "rating":     [{"avg_rating": "desc"}, "_score"],
            "fee_asc":    [{"consultation_fee": "asc"}],
            "fee_desc":   [{"consultation_fee": "desc"}],
            "experience": [{"experience_years": "desc"}],
        }
        sort_by = params.get("sort_by", "relevance")

        if sort_by == "distance" and params.get("lat") and params.get("lng"):
            sort = [{"_geo_distance": {
                "location": {"lat": params["lat"], "lon": params["lng"]},
                "order": "asc", "unit": "km",
            }}]
        else:
            sort = sort_map.get(sort_by, sort_map["relevance"])

        page      = params.get("page", 1)
        page_size = params.get("page_size", 10)

        response = await es.search(
            index=DOCTOR_INDEX,
            query=query,
            sort=sort,
            from_=(page - 1) * page_size,
            size=page_size,
        )

        total = response["hits"]["total"]["value"]
        hits  = [hit["_source"] for hit in response["hits"]["hits"]]
        return {"total": total, "hits": hits}

    except Exception as exc:
        print(f"⚠️   ES search failed ({exc}), falling back to PostgreSQL")
        return None
