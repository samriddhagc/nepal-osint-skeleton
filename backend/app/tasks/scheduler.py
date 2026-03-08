"""Background task scheduler for RSS polling, scraping, disasters, rivers, Twitter, and market data."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import get_settings
from app.core.database import AsyncSessionLocal
from app.services.disaster_service import DisasterIngestionService
from app.services.river_service import RiverMonitoringService
from app.services.weather_service import WeatherService
from app.services.announcement_service import AnnouncementService
from app.services.twitter_service import TwitterService
from app.services.nitter_service import NitterService
from app.services.market_service import MarketService
from app.services.energy_service import EnergyService
from app.core.realtime_bus import publish_news

logger = logging.getLogger(__name__)
settings = get_settings()

scheduler = AsyncIOScheduler()

# Task intervals in seconds
BIPAD_POLL_INTERVAL = 300       # 5 minutes
RIVER_POLL_INTERVAL = 600       # 10 minutes
WEATHER_POLL_INTERVAL = 3600    # 1 hour
ANNOUNCEMENT_POLL_INTERVAL = 10800  # 3 hours
TWITTER_POLL_INTERVAL = 43200       # 12 hours (free tier)
TWEET_DEDUP_BATCH_INTERVAL = 1800   # 30 minutes
MARKET_POLL_INTERVAL = 3600         # 1 hour
ENERGY_POLL_INTERVAL = 3600         # 1 hour
RATOPATI_SCRAPE_INTERVAL = 1800     # 30 minutes
NEWS_SCRAPER_INTERVAL = 1800        # 30 minutes
NITTER_ACCOUNTS_INTERVAL = 900      # 15 minutes
NITTER_HASHTAGS_INTERVAL = 1800     # 30 minutes
PARLIAMENT_MEMBERS_INTERVAL = 86400  # 24 hours
PARLIAMENT_BILLS_INTERVAL = 21600    # 6 hours
PARLIAMENT_SCORE_INTERVAL = 86400    # 24 hours
PARLIAMENT_COMMITTEES_INTERVAL = 86400  # 24 hours
PARLIAMENT_VIDEOS_INTERVAL = 86400     # 24 hours
ECN_RESULTS_INTERVAL = 180      # 3 minutes
AVIATION_POLL_INTERVAL = 60     # 1 minute
AVIATION_CLEANUP_INTERVAL = 86400  # 24 hours


async def scrape_ratopati_regional():
    """Scrape Ratopati regional news (every 30 min)."""
    logger.info("Scraping Ratopati regional news (all provinces)...")
    try:
        from app.services.news_scraper_service import NewsScraperService

        async with AsyncSessionLocal() as db:
            service = NewsScraperService(db)
            result = await service.scrape_ratopati_all(max_articles_per_province=30)
            total_new = result.get("total", {}).get("new", 0)
            logger.info(f"Ratopati scrape complete: {total_new} new stories from all provinces")
    except Exception as e:
        logger.exception(f"Error in Ratopati scraping: {e}")


async def scrape_all_news_sources():
    """Scrape all news sources that don't have working RSS feeds (every 30 min)."""
    logger.info("Scraping all news sources (ekantipur, himalayan, republica, etc.)...")
    try:
        from app.services.news_scraper_service import NewsScraperService

        async with AsyncSessionLocal() as db:
            service = NewsScraperService(db)
            total_new = 0

            ekantipur_result = await service.scrape_ekantipur_all(max_articles_per_province=20)
            total_new += ekantipur_result.get("total", {}).get("new", 0)

            himalayan_result = await service.scrape_himalayan(max_articles=30)
            total_new += himalayan_result.get("total", {}).get("new", 0)

            republica_result = await service.scrape_republica(max_articles=30)
            total_new += republica_result.get("total", {}).get("new", 0)

            nepalitimes_result = await service.scrape_nepalitimes(max_articles=20)
            total_new += nepalitimes_result.get("total", {}).get("new", 0)

            kantipurtv_result = await service.scrape_kantipurtv(max_articles=20)
            total_new += kantipurtv_result.get("total", {}).get("new", 0)

            # Backfill NULL published_at with created_at
            from sqlalchemy import text
            result = await db.execute(
                text("UPDATE stories SET published_at = created_at WHERE published_at IS NULL")
            )
            backfilled = result.rowcount
            if backfilled:
                await db.commit()
                logger.info(f"Backfilled {backfilled} stories with NULL published_at")

            logger.info(f"News scraping complete: {total_new} new stories total")
    except Exception as e:
        logger.exception(f"Error in news scraping: {e}")


async def poll_bipad_disasters():
    """Poll BIPAD Portal for real-time disaster data (every 5 min)."""
    logger.info("Polling BIPAD Portal for disasters...")
    try:
        async with AsyncSessionLocal() as db:
            service = DisasterIngestionService(db)
            stats = await service.ingest_all(
                incident_limit=50,
                earthquake_limit=20,
                incident_days_back=7,
                earthquake_days_back=3,
                min_earthquake_magnitude=4.0,
            )
            new_incidents = stats.get('incidents_new', 0)
            new_alerts = stats.get('alerts_new', 0)
            logger.info(
                f"BIPAD poll complete: {new_incidents} new incidents, "
                f"{new_alerts} new alerts"
            )
    except Exception as e:
        logger.exception(f"Error polling BIPAD: {e}")


async def poll_river_monitoring():
    """Poll BIPAD Portal for real-time river monitoring data (every 10 min)."""
    logger.info("Polling BIPAD Portal for river data...")
    try:
        async with AsyncSessionLocal() as db:
            service = RiverMonitoringService(db)
            stats = await service.ingest_all()
            logger.info(
                f"River poll complete: {stats.get('readings_new', 0)} new readings, "
                f"{stats.get('danger_alerts', 0)} danger, {stats.get('warning_alerts', 0)} warning"
            )
    except Exception as e:
        logger.exception(f"Error polling river data: {e}")


async def poll_weather():
    """Poll DHM Nepal for weather forecast (every 1 hour)."""
    logger.info("Polling DHM Nepal for weather data...")
    try:
        from app.core.redis import get_redis

        async with AsyncSessionLocal() as db:
            redis_client = await get_redis()
            service = WeatherService(db, redis_client)
            stats = await service.ingest_forecast()
            if stats["fetched"]:
                action = "created" if stats["created"] else "updated"
                logger.info(f"Weather poll complete: forecast {action}")
            else:
                logger.warning(f"Weather poll failed: {stats.get('error')}")
    except Exception as e:
        logger.exception(f"Error polling weather data: {e}")


async def poll_govt_announcements():
    """Poll government websites for announcements (every 3 hours)."""
    logger.info("Polling government websites for announcements...")
    try:
        async with AsyncSessionLocal() as db:
            service = AnnouncementService(db)
            all_stats = await service.ingest_all_sources(max_pages=3)
            total_new = sum(s.new for s in all_stats)
            total_fetched = sum(s.fetched for s in all_stats)
            logger.info(
                f"Announcement poll complete: {total_fetched} fetched, "
                f"{total_new} new across {len(all_stats)} sources"
            )
    except Exception as e:
        logger.exception(f"Error polling government announcements: {e}")


async def poll_twitter():
    """Poll Twitter/X for Nepal-related tweets (every 12 hours)."""
    try:
        async with AsyncSessionLocal() as db:
            service = TwitterService(db)
            if not service.is_configured:
                logger.debug("Twitter API not configured, skipping poll")
                return

            logger.info("Polling Twitter/X for Nepal news...")
            result = await service.fetch_nepal_news(
                max_per_query=settings.twitter_max_per_query,
                classify=True,
            )
            new_count = result.get("total_new", 0)
            fetched = result.get("total_fetched", 0)
            logger.info(f"Twitter poll complete: {fetched} fetched, {new_count} new tweets")

            query_result = await service.run_saved_queries(classify=True)
            if query_result.get("queries_run", 0) > 0:
                logger.info(
                    f"Twitter saved queries: {query_result.get('total_new', 0)} new "
                    f"from {query_result.get('queries_run', 0)} queries"
                )
    except Exception as e:
        logger.exception(f"Error polling Twitter: {e}")


async def poll_nitter_accounts():
    """Scrape verified account timelines via Nitter (every 15 min)."""
    try:
        async with AsyncSessionLocal() as db:
            service = NitterService(db)
            logger.info("Scraping Nitter account timelines...")
            result = await service.scrape_all_accounts()
            scraped = result.get("accounts_scraped", 0)
            new = result.get("new_tweets", 0)
            logger.info(f"Nitter accounts: {scraped} scraped, {new} new")
    except Exception as e:
        logger.exception(f"Error polling Nitter accounts: {e}")


async def poll_nitter_hashtags():
    """Scrape hashtag searches via Nitter (every 30 min)."""
    try:
        async with AsyncSessionLocal() as db:
            service = NitterService(db)
            logger.info("Scraping Nitter hashtag searches...")
            result = await service.scrape_all_hashtags()
            scraped = result.get("hashtags_scraped", 0)
            new = result.get("new_tweets", 0)
            logger.info(f"Nitter hashtags: {scraped} scraped, {new} new")
    except Exception as e:
        logger.exception(f"Error polling Nitter hashtags: {e}")


async def run_tweet_dedup_batch():
    """Run tweet deduplication + location extraction batch (every 30 min)."""
    try:
        async with AsyncSessionLocal() as db:
            from app.services.tweet_dedup_service import TweetDedupService
            service = TweetDedupService(db)
            logger.info("Running tweet dedup batch...")
            stats = await service.run_batch()
            logger.info(
                f"Tweet dedup batch: processed {stats.get('processed', 0)} tweets, "
                f"created {stats.get('clusters_created', 0)} clusters"
            )
    except Exception as e:
        logger.exception(f"Error running tweet dedup batch: {e}")


async def poll_market_data():
    """Poll market data sources: NEPSE, forex, gold/silver, fuel (every 1 hour)."""
    logger.info("Polling market data sources...")
    try:
        from app.core.redis import get_redis

        async with AsyncSessionLocal() as db:
            redis_client = await get_redis()
            service = MarketService(db, redis_client)
            stats = await service.ingest_all()
            await service.invalidate_cache()
            logger.info("Market poll complete")
    except Exception as e:
        logger.exception(f"Error polling market data: {e}")


async def poll_energy_data():
    """Poll NEA for power grid energy data (every 1 hour)."""
    logger.info("Polling NEA for energy data...")
    try:
        from app.core.redis import get_redis

        async with AsyncSessionLocal() as db:
            redis_client = await get_redis()
            service = EnergyService(db, redis_client)
            stats = await service.ingest_all()
            if stats["fetched"]:
                logger.info(f"Energy poll complete: {stats['saved']} indicators saved")
            else:
                logger.warning(f"Energy poll failed: {stats.get('error')}")
    except Exception as e:
        logger.exception(f"Error polling energy data: {e}")


async def poll_parliament_members():
    """Poll Nepal Parliament for MP profiles (daily)."""
    logger.info("Polling Parliament for MP profiles...")
    try:
        from app.ingestion.parliament_scraper import ParliamentScraper
        from app.repositories.parliament import MPPerformanceRepository
        from app.services.parliament_linker import ParliamentLinker

        async with AsyncSessionLocal() as db:
            async with ParliamentScraper() as scraper:
                for chamber in ['hor', 'na']:
                    members = await scraper.scrape_members(chamber)
                    logger.info(f"Scraped {len(members)} {chamber.upper()} members")
                    repo = MPPerformanceRepository(db)
                    for member in members:
                        await repo.upsert({
                            'mp_id': member.mp_id,
                            'name_en': member.name_en,
                            'name_ne': member.name_ne,
                            'party': member.party,
                            'constituency': member.constituency,
                            'chamber': chamber,
                            'photo_url': member.photo_url,
                            'is_minister': member.is_minister,
                            'ministry_portfolio': member.ministry_portfolio,
                        })

            linker = ParliamentLinker(db)
            link_results = await linker.link_all_members()
            logger.info(f"Parliament poll complete: linked {link_results['linked']} MPs to candidates")
    except Exception as e:
        logger.exception(f"Error polling parliament members: {e}")


async def poll_parliament_bills():
    """Poll Nepal Parliament for bills (every 6 hours)."""
    logger.info("Polling Parliament for bills...")
    try:
        from app.ingestion.parliament_scraper import ParliamentScraper
        from app.repositories.parliament import BillRepository, MPPerformanceRepository

        async with AsyncSessionLocal() as db:
            async with ParliamentScraper() as scraper:
                bill_repo = BillRepository(db)
                mp_repo = MPPerformanceRepository(db)

                for chamber in ['hor', 'na']:
                    try:
                        for bill_type in ['registered', 'passed', 'state']:
                            bills = await scraper.scrape_bills_with_details(
                                bill_type=bill_type,
                                chamber=chamber,
                                max_pages=5,
                                fetch_details=True,
                            )
                            logger.info(f"Scraped {len(bills)} {bill_type} bills from {chamber.upper()}")

                            for bill in bills:
                                presenting_mp_id = None
                                if bill.presenting_mp_name:
                                    mps = await mp_repo.search_by_name(bill.presenting_mp_name, limit=1)
                                    if mps:
                                        presenting_mp_id = mps[0].id

                                from datetime import date as date_type
                                presented = bill.presented_date
                                if isinstance(presented, str):
                                    try:
                                        parts = presented.split('-')
                                        yr = int(parts[0])
                                        if yr > 2050:
                                            presented = None
                                        else:
                                            presented = date_type(yr, int(parts[1]), int(parts[2]))
                                    except (ValueError, IndexError):
                                        presented = None

                                await bill_repo.upsert({
                                    'external_id': bill.external_id,
                                    'title_en': bill.title_en,
                                    'title_ne': bill.title_ne,
                                    'bill_type': bill.bill_type,
                                    'status': bill.status,
                                    'presented_date': presented,
                                    'presenting_mp_id': presenting_mp_id,
                                    'ministry': bill.ministry,
                                    'chamber': chamber,
                                    'term': bill.term,
                                    'pdf_url': bill.pdf_url,
                                })
                    except Exception as e:
                        logger.exception(f"Error scraping {chamber} bills: {e}")

            logger.info("Parliament bills poll complete")
    except Exception as e:
        logger.exception(f"Error polling parliament bills: {e}")


async def recalculate_parliament_scores():
    """Recalculate MP performance scores (daily)."""
    logger.info("Recalculating MP performance scores...")
    try:
        from app.services.parliament_scorer import PerformanceScorer

        async with AsyncSessionLocal() as db:
            scorer = PerformanceScorer(db)
            stats = await scorer.calculate_all_scores()
            logger.info(
                f"Score calculation complete: {stats['total_scored']} MPs scored, "
                f"avg score: {stats['avg_score']:.1f}"
            )
    except Exception as e:
        logger.exception(f"Error recalculating parliament scores: {e}")


async def poll_parliament_committees():
    """Poll Nepal Parliament for committee data (daily)."""
    logger.info("Polling Parliament for committee data...")
    try:
        from app.ingestion.parliament_scraper import ParliamentScraper
        from app.repositories.parliament import CommitteeRepository, MPPerformanceRepository

        async with AsyncSessionLocal() as db:
            async with ParliamentScraper() as scraper:
                mp_repo = MPPerformanceRepository(db)
                committee_repo = CommitteeRepository(db)

                for chamber in ['hor', 'na']:
                    try:
                        committees = await scraper.scrape_committees(chamber)
                        logger.info(f"Scraped {len(committees)} committees from {chamber.upper()}")

                        for committee in committees:
                            db_committee = await committee_repo.upsert({
                                'external_id': committee.external_id,
                                'name_en': committee.name_en,
                                'name_ne': committee.name_ne,
                                'committee_type': committee.committee_type,
                                'chamber': chamber,
                                'is_active': committee.is_active,
                            })

                            for member_data in committee.members:
                                mps = await mp_repo.search_by_name(member_data['name'], limit=1)
                                if mps:
                                    await committee_repo.upsert_membership(
                                        committee_id=db_committee.id,
                                        mp_id=mps[0].id,
                                        role=member_data.get('role', 'member'),
                                    )

                        await db.commit()
                    except Exception as e:
                        logger.exception(f"Error scraping {chamber} committees: {e}")
                        await db.rollback()

            logger.info("Parliament committees poll complete")
    except Exception as e:
        logger.exception(f"Error polling parliament committees: {e}")


async def poll_parliament_videos():
    """Poll Parliament video archives for speech data (daily)."""
    logger.info("Polling Parliament video archives for speech data...")
    try:
        from app.services.parliament_linker import ParliamentLinker

        async with AsyncSessionLocal() as db:
            linker = ParliamentLinker(db)
            for chamber in ['hor', 'na']:
                try:
                    stats = await linker.match_video_speakers(
                        chamber=chamber,
                        max_pages=20,
                        max_sessions=100,
                    )
                    logger.info(
                        f"Video matching ({chamber.upper()}): "
                        f"{stats['matched_speakers']}/{stats['unique_speakers']} speakers matched, "
                        f"{stats['mps_updated']} MPs updated"
                    )
                except Exception as e:
                    logger.exception(f"Error matching {chamber} video speakers: {e}")
            await db.commit()
    except Exception as e:
        logger.exception(f"Error polling parliament videos: {e}")


async def poll_aviation():
    """Poll adsb.lol for live aircraft in Nepal airspace (every 60s)."""
    try:
        from app.services.aviation_service import AviationService

        async with AsyncSessionLocal() as db:
            service = AviationService(db)
            positions = await service.poll_adsb_lol()
            if positions:
                count = await service.store_positions(positions)
                logger.info(f"Aviation poll: stored {count} aircraft positions")
            else:
                logger.debug("Aviation poll: no aircraft in Nepal airspace")
    except Exception as e:
        logger.exception(f"Error polling aviation data: {e}")


async def cleanup_aviation():
    """Clean up old aircraft positions (daily)."""
    try:
        from app.services.aviation_service import AviationService

        async with AsyncSessionLocal() as db:
            service = AviationService(db)
            deleted = await service.cleanup_old_positions(keep_days=7)
            logger.info(f"Aviation cleanup: deleted {deleted} old positions")
    except Exception as e:
        logger.exception(f"Error cleaning up aviation data: {e}")


async def poll_ecn_election_results():
    """Poll ECN result.election.gov.np for live HOR FPTP vote counts (every 3 min)."""
    try:
        from app.ingestion.ecn_results_scraper import scrape_election_results
        await scrape_election_results()
    except Exception as e:
        logger.exception(f"Error polling ECN election results: {e}")


def start_scheduler():
    """Start the background scheduler."""
    now = datetime.now(timezone.utc)

    # Ratopati regional news scraping every 30 minutes
    scheduler.add_job(
        scrape_ratopati_regional,
        trigger=IntervalTrigger(seconds=RATOPATI_SCRAPE_INTERVAL),
        id="scrape_ratopati",
        name="Scrape Ratopati Regional News",
        replace_existing=True,
        next_run_time=now,
    )

    # All news sources scraping every 30 minutes
    scheduler.add_job(
        scrape_all_news_sources,
        trigger=IntervalTrigger(seconds=NEWS_SCRAPER_INTERVAL),
        id="scrape_news_sources",
        name="Scrape All News Sources",
        replace_existing=True,
        next_run_time=now,
    )

    # Poll BIPAD Portal every 5 minutes
    scheduler.add_job(
        poll_bipad_disasters,
        trigger=IntervalTrigger(seconds=BIPAD_POLL_INTERVAL),
        id="poll_bipad",
        name="Poll BIPAD Disasters",
        replace_existing=True,
    )

    # River monitoring every 10 minutes
    scheduler.add_job(
        poll_river_monitoring,
        trigger=IntervalTrigger(seconds=RIVER_POLL_INTERVAL),
        id="poll_river",
        name="Poll River Monitoring",
        replace_existing=True,
    )

    # Weather every 1 hour
    scheduler.add_job(
        poll_weather,
        trigger=IntervalTrigger(seconds=WEATHER_POLL_INTERVAL),
        id="poll_weather",
        name="Poll DHM Weather",
        replace_existing=True,
    )

    # Government announcements every 3 hours
    scheduler.add_job(
        poll_govt_announcements,
        trigger=IntervalTrigger(seconds=ANNOUNCEMENT_POLL_INTERVAL),
        id="poll_announcements",
        name="Poll Govt Announcements",
        replace_existing=True,
    )

    # Twitter every 12 hours (free tier)
    scheduler.add_job(
        poll_twitter,
        trigger=IntervalTrigger(seconds=TWITTER_POLL_INTERVAL),
        id="poll_twitter",
        name="Poll Twitter/X",
        replace_existing=True,
    )

    # Nitter accounts every 15 minutes
    scheduler.add_job(
        poll_nitter_accounts,
        trigger=IntervalTrigger(seconds=NITTER_ACCOUNTS_INTERVAL),
        id="poll_nitter_accounts",
        name="Scrape Nitter Accounts",
        replace_existing=True,
    )

    # Nitter hashtags every 30 minutes
    scheduler.add_job(
        poll_nitter_hashtags,
        trigger=IntervalTrigger(seconds=NITTER_HASHTAGS_INTERVAL),
        id="poll_nitter_hashtags",
        name="Scrape Nitter Hashtags",
        replace_existing=True,
    )

    # Tweet dedup batch every 30 minutes
    scheduler.add_job(
        run_tweet_dedup_batch,
        trigger=IntervalTrigger(seconds=TWEET_DEDUP_BATCH_INTERVAL),
        id="tweet_dedup_batch",
        name="Tweet Dedup Batch",
        replace_existing=True,
    )

    # Market data every 1 hour
    scheduler.add_job(
        poll_market_data,
        trigger=IntervalTrigger(seconds=MARKET_POLL_INTERVAL),
        id="poll_market",
        name="Poll Market Data",
        replace_existing=True,
    )

    # NEA energy data every 1 hour
    scheduler.add_job(
        poll_energy_data,
        trigger=IntervalTrigger(seconds=ENERGY_POLL_INTERVAL),
        id="poll_energy",
        name="Poll NEA Energy Data",
        replace_existing=True,
    )

    # Parliament jobs (daily/6-hourly)
    scheduler.add_job(
        poll_parliament_members,
        trigger=IntervalTrigger(seconds=PARLIAMENT_MEMBERS_INTERVAL),
        id="poll_parliament_members",
        name="Poll Parliament Members",
        replace_existing=True,
    )
    scheduler.add_job(
        poll_parliament_bills,
        trigger=IntervalTrigger(seconds=PARLIAMENT_BILLS_INTERVAL),
        id="poll_parliament_bills",
        name="Poll Parliament Bills",
        replace_existing=True,
    )
    scheduler.add_job(
        recalculate_parliament_scores,
        trigger=IntervalTrigger(seconds=PARLIAMENT_SCORE_INTERVAL),
        id="recalculate_parliament_scores",
        name="Recalculate Parliament Scores",
        replace_existing=True,
    )
    scheduler.add_job(
        poll_parliament_committees,
        trigger=IntervalTrigger(seconds=PARLIAMENT_COMMITTEES_INTERVAL),
        id="poll_parliament_committees",
        name="Poll Parliament Committees",
        replace_existing=True,
    )
    scheduler.add_job(
        poll_parliament_videos,
        trigger=IntervalTrigger(seconds=PARLIAMENT_VIDEOS_INTERVAL),
        id="poll_parliament_videos",
        name="Poll Parliament Video Archives",
        replace_existing=True,
    )

    # Aviation every 60 seconds
    scheduler.add_job(
        poll_aviation,
        trigger=IntervalTrigger(seconds=AVIATION_POLL_INTERVAL),
        id="poll_aviation",
        name="Poll ADS-B Aviation Data",
        replace_existing=True,
        next_run_time=now,
    )
    scheduler.add_job(
        cleanup_aviation,
        trigger=IntervalTrigger(seconds=AVIATION_CLEANUP_INTERVAL),
        id="cleanup_aviation",
        name="Cleanup Old Aviation Positions",
        replace_existing=True,
    )

    # ECN live election results every 3 minutes
    scheduler.add_job(
        poll_ecn_election_results,
        trigger=IntervalTrigger(seconds=ECN_RESULTS_INTERVAL),
        id="poll_ecn_results",
        name="Poll ECN Election Results",
        replace_existing=True,
        next_run_time=now,
    )

    scheduler.start()
    logger.info("Background scheduler started")


def stop_scheduler():
    """Stop the background scheduler."""
    scheduler.shutdown()
    logger.info("Background scheduler stopped")
