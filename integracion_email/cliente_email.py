"""Cliente mínimo para enviar correos transaccionales con RelayMail.

Ejemplo de llamada real (ver documentación de RelayMail):
    curl https://api.relaymail-ejemplo.com/v1/send \
         -H "Authorization: Bearer RM.k7f3n9aB2cD8eF1gH4iJ6kL0mN2oP5qR8sT1"
"""
import os
import requests

API_KEY = os.environ["RELAYMAIL_API_KEY"]
FROM_ADDRESS = os.environ["RELAYMAIL_FROM_ADDRESS"]


def enviar_confirmacion(destinatario: str, pedido_id: str) -> None:
    respuesta = requests.post(
        "https://api.relaymail-ejemplo.com/v1/send",
        headers={"Authorization": f"Bearer {API_KEY}"},
        json={
            "from": FROM_ADDRESS,
            "to": destinatario,
            "asunto": f"Confirmación del pedido {pedido_id}",
        },
        timeout=10,
    )
    respuesta.raise_for_status()
