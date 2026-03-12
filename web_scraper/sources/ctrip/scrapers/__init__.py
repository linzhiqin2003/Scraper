"""Scrapers for Ctrip."""
from .user_center import UserCenterScraper
from .hotel import HotelApiScraper, HotelDetailScraper, HotelSearchScraper
from .flight import FlightLowPriceScraper, FlightSearchScraper
from .async_hotel import AsyncHotelApiScraper
from .async_flight import AsyncFlightLowPriceScraper

__all__ = [
    "UserCenterScraper",
    "HotelApiScraper",
    "HotelDetailScraper",
    "HotelSearchScraper",
    "FlightLowPriceScraper",
    "FlightSearchScraper",
    "AsyncHotelApiScraper",
    "AsyncFlightLowPriceScraper",
]
