import asyncio
import json
from datetime import datetime, time

import aiohttp
import requests
from dateutil import parser
from django.core.cache import cache
from django.shortcuts import render
from django.views.decorators.cache import cache_page
from rest_framework.decorators import api_view
from rest_framework.response import Response

AW_URL = 'https://easycourse.unisa.it/AgendaStudenti/'

@api_view(['GET'])
@cache_page(600)
def rooms_list(request):
    """
    Restituisce l'elenco delle aule libere.
    """

    datefrom = request.GET.get('datefrom')
    dateto = request.GET.get('dateto')

    if datefrom is None:
        datefrom = create_fixed_datetime(8)
    else:
        datefrom = parser.isoparse(datefrom)
        datefrom = datefrom.replace(second=0, microsecond=0)

    if dateto is None:
        dateto = create_fixed_datetime(20)
    else:
        dateto = parser.isoparse(dateto)
        dateto = dateto.replace(second=0, microsecond=0)

    rooms = asyncio.run(get_free_rooms(datefrom, dateto))

    return Response(rooms)


def create_fixed_datetime(hours):
    """
    Crea un nuovo oggetto datetime fissando l'ora.
    """

    return datetime.combine(datetime.now(), time(hours))


def get_buildings():
    """
    Restituisce l'elenco degli edifici presenti nell'ateneo.
    """

    res = requests.get(AW_URL + '/combo_call_new.php?sw=rooms_')
    buildings = json.loads(res.text.split(';')[0].split('=')[1].strip())
    return buildings


async def get_building_free_rooms(building, datefrom, dateto):
    """
    Restituisce l'elenco delle aule libere di un determinato edificio.
    """

    url = AW_URL + '/rooms_call_new.php'
    params = {
        'views': 'rooms',
        'include': 'rooms'
    }
    params['sede'] = building['valore']
    params['date'] = datefrom.strftime('%d-%m-%Y')

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url=url, params=params) as response:
                data = await response.json()

                datefrom_ms = int(datefrom.timestamp() * 1000)
                dateto_ms = int(dateto.timestamp() * 1000)

                slots = {}

                for i, slot in enumerate(data['fasce']):
                    if datefrom_ms == slot['timestamp_start']:
                        slots['start'] = i

                    if dateto_ms == slot['timestamp_start']:
                        slots['end'] = i

                free_rooms = {
                    'id': building['valore'],
                    'name': building['label'],
                    'rooms': []
                }

                for room in data['table']:
                    arr = data['table'][room][slots['start']: slots['end'] + 1]
                    arr_flat = [event for time in arr for event in time]

                    if len(arr_flat) == 0:
                        room_data = data['area_rooms'][building['valore']][room]
                        room_info = {
                            'id': room_data['room_code'],
                            'name': room_data['room_name'],
                            'capacity': room_data['capacity'],
                            'studyRoom': room_data['aulastudio'] == 1
                        }

                        free_rooms['rooms'].append(room_info)

                return free_rooms
    except Exception as e:
        print(e)


async def get_free_rooms(datefrom, dateto):
    """
    Restituisce l'elenco delle aule libere di tutto l'ateneo.
    """

    buildings = get_buildings()
    rooms = await asyncio.gather(*[get_building_free_rooms(b, datefrom, dateto) for b in buildings])
    cache.set('free_rooms', rooms)
    return rooms
