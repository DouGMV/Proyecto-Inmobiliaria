import type { RespuestaAgente } from '../../api/ia/mutaciones'

const ENTERO = new Intl.NumberFormat('es-GT')

/**
 * Costo en dólares con seis decimales: una consulta cuesta fracciones de
 * centavo y con dos decimales siempre se vería "US$0.00".
 */
const DOLARES = new Intl.NumberFormat('es-GT', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 6,
  maximumFractionDigits: 6,
})

type Props = Pick<
  RespuestaAgente,
  'tokens_entrada' | 'tokens_salida' | 'costo_estimado_usd'
>

/**
 * Serie II, inciso 9: los tokens que consumió la consulta y su costo
 * aproximado, que calcula la API con los precios de settings. null significa
 * que el proveedor no reportó el consumo; cero, que no se llamó al modelo.
 */
export function ConsumoConsulta({
  tokens_entrada,
  tokens_salida,
  costo_estimado_usd,
}: Props) {
  let texto: string
  if (tokens_entrada === null || tokens_salida === null) {
    texto = 'Consumo no disponible: el proveedor no reportó los tokens.'
  } else if (tokens_entrada === 0 && tokens_salida === 0) {
    texto = 'Sin consumo: no se llamó al modelo.'
  } else {
    const costo =
      costo_estimado_usd === null
        ? 'no disponible'
        : DOLARES.format(Number(costo_estimado_usd))
    texto =
      `Tokens: ${ENTERO.format(tokens_entrada)} de entrada · ` +
      `${ENTERO.format(tokens_salida)} de salida · costo aprox. ${costo}`
  }
  return (
    <p
      className="border-t border-slate-200 pt-2 text-xs text-slate-500"
      data-testid="consumo"
    >
      {texto}
    </p>
  )
}
