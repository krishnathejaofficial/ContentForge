"""
engines/content_fetcher.py — Multi-source content fetcher with 30+ category handlers.

Cascade order for each category:
  1. Primary API (category-specific)
  2. API-Ninjas generic facts endpoint
  3. Local JSON dataset (assets/fact_datasets.json)
  4. Hardcoded default fact
"""
import json
import random
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

import requests

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import NEWS_API_KEY, API_NINJAS_KEY, FACT_JSON
from utils.cache_manager import cache

logger = logging.getLogger(__name__)


# ─── Base Handler ─────────────────────────────────────────────────────────────

class CategoryHandler(ABC):
    category: str = ""

    def fetch(self) -> Dict[str, Any]:
        """Try API → dataset → default."""
        # Try cache first
        cached = cache.get("content", self.category)
        if cached:
            return cached

        result = None
        try:
            result = self.fetch_from_api()
        except Exception as e:
            logger.warning(f"[{self.category}] API failed: {e}")

        if not result:
            try:
                result = self.fetch_from_dataset()
            except Exception as e:
                logger.warning(f"[{self.category}] Dataset failed: {e}")

        if not result:
            result = self.get_default_fact()

        cache.set(result, "content", self.category)
        return result

    @abstractmethod
    def fetch_from_api(self) -> Optional[Dict]:
        pass

    def fetch_from_dataset(self) -> Optional[Dict]:
        if not FACT_JSON.exists():
            return None
        try:
            data = json.loads(FACT_JSON.read_text())
            facts = data.get(self.category, [])
            if facts:
                text = random.choice(facts)
                return {"text": text, "source": "local-dataset"}
        except Exception:
            pass
        return None

    @abstractmethod
    def get_default_fact(self) -> Dict:
        pass


# ─── API Helpers ──────────────────────────────────────────────────────────────

def _ninjas_facts(category: str) -> Optional[Dict]:
    if not API_NINJAS_KEY:
        return None
    url = f"https://api.api-ninjas.com/v1/facts?limit=1"
    r = requests.get(url, headers={"X-Api-Key": API_NINJAS_KEY}, timeout=8)
    r.raise_for_status()
    data = r.json()
    if data:
        return {"text": data[0]["fact"], "source": "api-ninjas"}
    return None


def _ninjas_endpoint(endpoint: str, params: dict = {}) -> Optional[dict]:
    if not API_NINJAS_KEY:
        return None
    url = f"https://api.api-ninjas.com/v1/{endpoint}"
    r = requests.get(url, headers={"X-Api-Key": API_NINJAS_KEY}, params=params, timeout=8)
    r.raise_for_status()
    return r.json()


def _news_headlines(query: str) -> Optional[Dict]:
    if not NEWS_API_KEY:
        return None
    url = "https://newsapi.org/v2/everything"
    params = {"q": query, "pageSize": 5, "sortBy": "publishedAt", "apiKey": NEWS_API_KEY}
    r = requests.get(url, params=params, timeout=8)
    r.raise_for_status()
    articles = r.json().get("articles", [])
    if articles:
        a = random.choice(articles)
        text = a.get("description") or a.get("title", "")
        return {"text": text, "source": "newsapi", "extra_data": {"url": a.get("url", "")}}
    return None


# ─── Category Handlers ────────────────────────────────────────────────────────

class FactsHandler(CategoryHandler):
    category = "facts"
    def fetch_from_api(self):
        return _ninjas_facts("facts")
    def get_default_fact(self):
        return {"text": "The human brain processes around 70,000 thoughts per day.", "source": "default"}

class ScienceHandler(CategoryHandler):
    category = "science"
    def fetch_from_api(self):
        data = _ninjas_endpoint("facts", {"limit": 1})
        if data:
            return {"text": data[0]["fact"], "source": "api-ninjas-science"}
        return _news_headlines("science discovery")
    def get_default_fact(self):
        return {"text": "Light travels at 299,792 kilometres per second in a vacuum.", "source": "default"}

class BiologyHandler(CategoryHandler):
    category = "biology"
    def fetch_from_api(self):
        return _ninjas_facts("biology")
    def get_default_fact(self):
        return {"text": "The human body contains approximately 37.2 trillion cells.", "source": "default"}

class HistoryHandler(CategoryHandler):
    category = "history"
    def fetch_from_api(self):
        data = _ninjas_endpoint("historicalevents", {"month": random.randint(1,12), "day": random.randint(1,28)})
        if data:
            ev = random.choice(data) if isinstance(data, list) else data
            return {"text": f"On this day in {ev['year']}: {ev['event']}", "source": "api-ninjas-history"}
        return None
    def get_default_fact(self):
        return {"text": "The Great Wall of China took over 1,000 years to build completely.", "source": "default"}

class TechnologyHandler(CategoryHandler):
    category = "technology"
    def fetch_from_api(self):
        return _news_headlines("technology innovation")
    def get_default_fact(self):
        return {"text": "The first computer bug was an actual moth found in a Harvard computer in 1947.", "source": "default"}

class SpaceHandler(CategoryHandler):
    category = "space"
    def fetch_from_api(self):
        try:
            r = requests.get("https://api.nasa.gov/planetary/apod?api_key=DEMO_KEY", timeout=8)
            r.raise_for_status()
            data = r.json()
            return {"text": data.get("explanation", "")[:300], "source": "nasa-apod"}
        except Exception:
            return _news_headlines("space astronomy NASA")
    def get_default_fact(self):
        return {"text": "One million Earths could fit inside the Sun.", "source": "default"}

class PsychologyHandler(CategoryHandler):
    category = "psychology"
    def fetch_from_api(self):
        return _ninjas_facts("psychology")
    def get_default_fact(self):
        return {"text": "The average person has between 12,000 and 60,000 thoughts per day, and 80% of them are negative.", "source": "default"}

class HealthHandler(CategoryHandler):
    category = "health"
    def fetch_from_api(self):
        return _news_headlines("health wellness science")
    def get_default_fact(self):
        return {"text": "Laughing 100 times is the equivalent of a 10-minute workout on a rowing machine.", "source": "default"}

class NatureHandler(CategoryHandler):
    category = "nature"
    def fetch_from_api(self):
        return _ninjas_facts("nature")
    def get_default_fact(self):
        return {"text": "Trees can communicate and share nutrients through underground fungal networks.", "source": "default"}

class MathematicsHandler(CategoryHandler):
    category = "mathematics"
    def fetch_from_api(self):
        return _ninjas_facts("mathematics")
    def get_default_fact(self):
        return {"text": "The number Pi has been calculated to over 100 trillion decimal places.", "source": "default"}

class GeographyHandler(CategoryHandler):
    category = "geography"
    def fetch_from_api(self):
        data = _ninjas_endpoint("country", {"name": random.choice(["brazil","japan","canada","india","australia"])})
        if data:
            d = data[0] if isinstance(data, list) else data
            return {"text": f"{d['name']} has a population of {d['population']:,} and covers {d['area']:,} km².", "source": "api-ninjas-country"}
        return None
    def get_default_fact(self):
        return {"text": "Russia is the largest country in the world, covering 11% of Earth's land area.", "source": "default"}

class AnimalsHandler(CategoryHandler):
    category = "animals"
    def fetch_from_api(self):
        animals = ["elephant","dolphin","octopus","cheetah","eagle"]
        data = _ninjas_endpoint("animals", {"name": random.choice(animals)})
        if data:
            a = data[0]
            return {"text": f"The {a['name']} ({a.get('taxonomy',{}).get('scientific_name','')}) {a.get('characteristics',{}).get('most_distinctive_feature','is a fascinating creature.')}.", "source": "api-ninjas-animals"}
        return None
    def get_default_fact(self):
        return {"text": "Octopuses have three hearts, nine brains, and blue blood.", "source": "default"}

class FoodHandler(CategoryHandler):
    category = "food"
    def fetch_from_api(self):
        data = _ninjas_endpoint("nutrition", {"query": random.choice(["apple","broccoli","salmon","almonds","banana"])})
        if data:
            item = data[0]
            return {"text": f"One serving of {item['name']} contains {item['calories']} calories, {item['protein_g']}g of protein, and {item['fiber_g']}g of fiber.", "source": "api-ninjas-nutrition"}
        return None
    def get_default_fact(self):
        return {"text": "Honey never spoils — edible honey has been found in 3,000-year-old Egyptian tombs.", "source": "default"}

class SportsHandler(CategoryHandler):
    category = "sports"
    def fetch_from_api(self):
        return _news_headlines("sports world record athlete")
    def get_default_fact(self):
        return {"text": "Usain Bolt's top speed was 44.72 km/h, set during the 2009 World Championships.", "source": "default"}

class MusicHandler(CategoryHandler):
    category = "music"
    def fetch_from_api(self):
        return _news_headlines("music science brain")
    def get_default_fact(self):
        return {"text": "Music can reduce anxiety by up to 65% according to studies at Mindlab International.", "source": "default"}

class MoviesHandler(CategoryHandler):
    category = "movies"
    def fetch_from_api(self):
        return _news_headlines("film cinema world record box office")
    def get_default_fact(self):
        return {"text": "The first motion picture ever made was a 2-second clip of a horse galloping, shot in 1878.", "source": "default"}

class BooksHandler(CategoryHandler):
    category = "books"
    def fetch_from_api(self):
        return _news_headlines("books reading brain benefits")
    def get_default_fact(self):
        return {"text": "Reading for just 6 minutes can reduce stress levels by 68%, according to University of Sussex researchers.", "source": "default"}

class PhilosophyHandler(CategoryHandler):
    category = "philosophy"
    def fetch_from_api(self):
        return _ninjas_facts("philosophy")
    def get_default_fact(self):
        return {"text": "Socrates never wrote anything down — everything we know about him comes from his students.", "source": "default"}

class EconomicsHandler(CategoryHandler):
    category = "economics"
    def fetch_from_api(self):
        return _news_headlines("economics global market GDP")
    def get_default_fact(self):
        return {"text": "If wealth were distributed equally, every person on Earth would have roughly $23,000.", "source": "default"}

class PoliticsHandler(CategoryHandler):
    category = "politics"
    def fetch_from_api(self):
        return _news_headlines("politics government policy")
    def get_default_fact(self):
        return {"text": "The world's oldest democracy is widely considered to be ancient Athens, dating back to 507 BC.", "source": "default"}

class EnvironmentHandler(CategoryHandler):
    category = "environment"
    def fetch_from_api(self):
        return _news_headlines("environment climate change ecology")
    def get_default_fact(self):
        return {"text": "The Amazon rainforest produces 20% of the world's oxygen and is home to 10% of all species.", "source": "default"}

class ArchitectureHandler(CategoryHandler):
    category = "architecture"
    def fetch_from_api(self):
        return _news_headlines("architecture design building world")
    def get_default_fact(self):
        return {"text": "The Burj Khalifa sways up to 1.5 metres at its peak during strong winds.", "source": "default"}

class ArtHandler(CategoryHandler):
    category = "art"
    def fetch_from_api(self):
        return _news_headlines("art painting auction record")
    def get_default_fact(self):
        return {"text": "The Mona Lisa has no eyebrows — it was fashionable in Renaissance Florence to shave them off.", "source": "default"}

class FashionHandler(CategoryHandler):
    category = "fashion"
    def fetch_from_api(self):
        return _news_headlines("fashion industry trend sustainability")
    def get_default_fact(self):
        return {"text": "The fashion industry produces 10% of all humanity's carbon emissions, more than shipping and aviation combined.", "source": "default"}

class TravelHandler(CategoryHandler):
    category = "travel"
    def fetch_from_api(self):
        data = _ninjas_endpoint("city", {"name": random.choice(["Tokyo","Paris","New York","Sydney","Dubai"])})
        if data:
            d = data[0] if isinstance(data, list) else data
            return {"text": f"{d['name']}, {d['country']} has a population of {d['population']:,} and sits at an elevation of {d['elevation']}m.", "source": "api-ninjas-city"}
        return None
    def get_default_fact(self):
        return {"text": "Japan has more vending machines per capita than any other country — roughly one for every 23 people.", "source": "default"}

class FitnessHandler(CategoryHandler):
    category = "fitness"
    def fetch_from_api(self):
        data = _ninjas_endpoint("exercises", {"type": random.choice(["strength","cardio","stretching"]), "limit": 1})
        if data:
            ex = data[0]
            return {"text": f"Try the '{ex['name']}': {ex.get('instructions','A great exercise for overall fitness.')}.", "source": "api-ninjas-exercises"}
        return None
    def get_default_fact(self):
        return {"text": "Just 30 minutes of moderate exercise per day can reduce the risk of chronic disease by up to 35%.", "source": "default"}

class NutritionHandler(CategoryHandler):
    category = "nutrition"
    def fetch_from_api(self):
        data = _ninjas_endpoint("nutrition", {"query": random.choice(["spinach","quinoa","avocado","blueberries","eggs"])})
        if data:
            item = data[0]
            return {"text": f"{item['name'].title()} is packed with nutrients: {item['calories']} kcal, {item['protein_g']}g protein, {item['fat_total_g']}g fat per 100g.", "source": "api-ninjas-nutrition"}
        return None
    def get_default_fact(self):
        return {"text": "Eating blueberries regularly can improve memory by up to 5 years, according to Harvard studies.", "source": "default"}

class LanguageHandler(CategoryHandler):
    category = "language"
    def fetch_from_api(self):
        return _ninjas_facts("language")
    def get_default_fact(self):
        return {"text": "There are approximately 7,000 languages spoken in the world today, and one goes extinct every 14 days.", "source": "default"}

class MythologyHandler(CategoryHandler):
    category = "mythology"
    def fetch_from_api(self):
        return _ninjas_facts("mythology")
    def get_default_fact(self):
        return {"text": "The word 'volcano' comes from Vulcan, the Roman god of fire and metalworking.", "source": "default"}

class InventionsHandler(CategoryHandler):
    category = "inventions"
    def fetch_from_api(self):
        return _news_headlines("invention patent technology breakthrough")
    def get_default_fact(self):
        return {"text": "The microwave oven was invented accidentally when Percy Spencer noticed radar waves melted a chocolate bar in his pocket.", "source": "default"}


# ─── Registry & Main Class ────────────────────────────────────────────────────

_HANDLERS: Dict[str, CategoryHandler] = {
    h.category: h() for h in [
        FactsHandler, ScienceHandler, BiologyHandler, HistoryHandler,
        TechnologyHandler, SpaceHandler, PsychologyHandler, HealthHandler,
        NatureHandler, MathematicsHandler, GeographyHandler, AnimalsHandler,
        FoodHandler, SportsHandler, MusicHandler, MoviesHandler,
        BooksHandler, PhilosophyHandler, EconomicsHandler, PoliticsHandler,
        EnvironmentHandler, ArchitectureHandler, ArtHandler, FashionHandler,
        TravelHandler, FitnessHandler, NutritionHandler, LanguageHandler,
        MythologyHandler, InventionsHandler,
    ]
}


class ContentFetcher:
    """Main entry point for content fetching."""

    def fetch_content(self, category: str) -> Dict[str, Any]:
        """
        Fetch content for the given category.
        Returns: {"text": str, "source": str, "extra_data": {...}}
        """
        category = category.lower().strip()
        handler = _HANDLERS.get(category)
        if not handler:
            logger.warning(f"No handler for '{category}', falling back to facts.")
            handler = _HANDLERS["facts"]
        return handler.fetch()
