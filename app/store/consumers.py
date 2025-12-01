import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model

User = get_user_model()


class OrderConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for order updates"""
    
    async def connect(self):
        """Handle WebSocket connection"""
        # Join the order updates group
        self.group_name = 'order_updates'
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        # Leave the order updates group
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )
    
    async def receive(self, text_data):
        """Handle messages received from WebSocket"""
        # For now, we don't need to handle incoming messages
        # Clients will just listen for updates
        pass
    
    async def order_update(self, event):
        """Send order update to WebSocket"""
        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'order_update',
            'order_id': event['order_id'],
            'status': event['status'],
            'action': event['action'],  # 'removed', 'updated', 'added'
        }))

