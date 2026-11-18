import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'

import { leerErrorApi } from '../../api/errores'
import { useConsultarAgente, type RespuestaAgente } from '../../api/ia/mutaciones'
import { Button } from '../../componentes/ui/button'
import { Card, CardContent } from '../../componentes/ui/card'
import { Label } from '../../componentes/ui/label'
import { useSesion } from '../../sesion/useSesion'
import { ConsumoConsulta } from './ConsumoConsulta'
import { RespuestaConCitas } from './RespuestaConCitas'

/** Spec 005, regla 8: entre 3 y 500 caracteres. */
const MINIMO = 3
const MAXIMO = 500

interface Turno {
  pregunta: string
  respuesta?: RespuestaAgente
  error?: string
}

/**
 * El error del agente, dicho para un visitante (spec 018, regla 9): un 429
 * dice cuántos segundos esperar; los demás, el mensaje de la API (un 503 es
 * "el asistente no está disponible").
 */
function mensajeDeError(error: unknown): string {
  const { codigo, mensaje, detalles } = leerErrorApi(error)
  if (codigo === 'DEMASIADAS_PETICIONES') {
    const espera = Number(detalles.espera_segundos)
    return Number.isFinite(espera)
      ? `Hizo muchas preguntas seguidas. Espere ${espera} segundos y vuelva a intentar.`
      : 'Hizo muchas preguntas seguidas. Espere un momento y vuelva a intentar.'
  }
  return mensaje
}

/**
 * El asistente público (spec 018, reglas 8 a 10; spec 005). Se abre sin
 * iniciar sesión: es para los visitantes del sitio. Las preguntas de la
 * visita quedan en pantalla mientras está abierta; no se guardan en el
 * navegador.
 */
export function Asistente() {
  const { estado } = useSesion()
  const consultar = useConsultarAgente()
  const [pregunta, setPregunta] = useState('')
  const [turnos, setTurnos] = useState<Turno[]>([])

  const texto = pregunta.trim()
  const valida = texto.length >= MINIMO && texto.length <= MAXIMO

  const preguntar = async (evento: FormEvent<HTMLFormElement>) => {
    evento.preventDefault()
    if (!valida || consultar.isPending) {
      return
    }
    setPregunta('')
    try {
      const respuesta = await consultar.mutateAsync(texto)
      setTurnos((anteriores) => [{ pregunta: texto, respuesta }, ...anteriores])
    } catch (error) {
      setTurnos((anteriores) => [
        { pregunta: texto, error: mensajeDeError(error) },
        ...anteriores,
      ])
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-3xl flex-col gap-4 p-4">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="font-editorial text-4xl leading-none">
            Asistente de la agencia
          </h1>
          <p className="text-sm text-tenue">
            Responde con los documentos de la agencia y cita de dónde sale cada dato.
          </p>
        </div>
        <Link className="text-sm text-oxido hover:underline" to="/">
          {estado === 'con-sesion' ? 'Volver al sistema' : 'Iniciar sesión'}
        </Link>
      </header>

      {/* Regla 10: visible antes de la primera pregunta, y siempre. */}
      <p className="rounded-md bg-amber-50 p-3 text-sm text-amber-800">
        No escriba datos personales (nombres, teléfonos, números de documento). Las
        preguntas se procesan con un servicio externo de inteligencia artificial.
      </p>

      <form onSubmit={preguntar} className="flex flex-col gap-2">
        <Label htmlFor="pregunta">Su pregunta</Label>
        <textarea
          id="pregunta"
          rows={3}
          maxLength={MAXIMO}
          value={pregunta}
          onChange={(evento) => setPregunta(evento.target.value)}
          placeholder="Por ejemplo: ¿qué documentos necesito para comprar en Guatemala?"
          className="w-full rounded-md border border-ceniza bg-blanco px-3 py-2 text-sm focus-visible:ring-2 focus-visible:ring-tenue focus-visible:outline-none"
        />
        <div className="flex items-center justify-between">
          <span className="text-xs text-tenue">
            {texto.length}/{MAXIMO}
          </span>
          <Button type="submit" disabled={!valida || consultar.isPending}>
            {consultar.isPending ? 'Buscando…' : 'Preguntar'}
          </Button>
        </div>
      </form>

      {/* La más reciente arriba. */}
      {turnos.map((turno, indice) => {
        const prefijo = `r${turnos.length - indice}`
        return (
          <Card key={prefijo}>
            <CardContent className="flex flex-col gap-3 pt-6">
              <p className="text-sm font-medium">{turno.pregunta}</p>
              {turno.error && (
                <p
                  role="alert"
                  className="rounded-md bg-red-50 p-3 text-sm text-red-700"
                >
                  {turno.error}
                </p>
              )}
              {turno.respuesta &&
                (turno.respuesta.sin_informacion ? (
                  <p className="text-sm text-tenue">{turno.respuesta.respuesta}</p>
                ) : (
                  <RespuestaConCitas
                    respuesta={turno.respuesta.respuesta}
                    citas={turno.respuesta.citas}
                    prefijo={prefijo}
                  />
                ))}
              {/* Serie II, inciso 9: tokens y costo de esta consulta. */}
              {turno.respuesta && <ConsumoConsulta {...turno.respuesta} />}
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}
