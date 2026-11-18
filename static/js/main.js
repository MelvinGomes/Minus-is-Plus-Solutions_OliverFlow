/**
 * OliverFlow - Interacoes de cliente (ES6+)
 * Mascaras de telefone/valor, carregamento dinamico de pets/horarios e modais.
 */
(function () {
    "use strict";

    function formatarMoeda(valor) {
        const n = Number(strParaNumero(valor));
        if (Number.isNaN(n)) return "R$ 0,00";
        return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
    }

    function strParaNumero(v) {
        if (typeof v === "number") return v;
        if (!v) return 0;
        const s = String(v).replace(/[^\d,.-]/g, "");
        return s.includes(",") ? parseFloat(s.replace(/\./g, "").replace(",", ".")) : parseFloat(s);
    }

    // --- Mascara de telefone (11) 99999-9999 -------------------------------
    function aplicarMascaraTelefone(input) {
        input.addEventListener("input", () => {
            let d = input.value.replace(/\D/g, "").slice(0, 11);
            if (d.length > 6) {
                d = d.length === 11
                    ? `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}`
                    : `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}`;
            } else if (d.length > 2) {
                d = `(${d.slice(0, 2)}) ${d.slice(2)}`;
            }
            input.value = d;
        });
    }

    // --- Modal de Novo Agendamento -----------------------------------------
    function iniciarModalAgendamento() {
        const modalEl = document.getElementById("modalNovoAgendamento");
        if (!modalEl) return;

        const selTutor = document.getElementById("ag_tutor_id");
        const selPet = document.getElementById("ag_pet_id");
        const inpPorte = document.getElementById("ag_pet_porte");
        const inpData = document.getElementById("ag_data");
        const inpValor = document.getElementById("ag_valor_cobrado");
        const slotsWrap = document.getElementById("ag_slots_container");
        const resPet = document.getElementById("res_pet");
        const resData = document.getElementById("res_data_hora");
        const resServico = document.getElementById("res_servico");
        const resValor = document.getElementById("res_valor");
        const resTotal = document.getElementById("res_total");
        let horaPreSelecionada = "";

        function servicoSelecionado() {
            return modalEl.querySelector('input[name="servico_id"]:checked');
        }

        function horaSelecionada() {
            const r = modalEl.querySelector('input[name="hora_inicio"]:checked');
            return r ? r.value : "";
        }

        function atualizarResumo() {
            const optPet = selPet.options[selPet.selectedIndex];
            resPet.textContent = optPet && optPet.value ? optPet.dataset.nome || optPet.textContent : "Selecione o pet";
            inpPorte.value = optPet && optPet.value ? (optPet.dataset.porte || "") : "";

            const srv = servicoSelecionado();
            if (srv) {
                resServico.textContent = `${srv.dataset.nome} (${srv.dataset.duracaoTexto})`;
            } else {
                resServico.textContent = "Selecione um serviço";
            }

            const valorAtual = inpValor.value ? strParaNumero(inpValor.value) : (srv ? Number(srv.dataset.valor) : 0);
            resValor.textContent = formatarMoeda(valorAtual);
            resTotal.textContent = formatarMoeda(valorAtual);

            const dataStr = inpData.value ? inpData.value.split("-").reverse().join("/") : "—";
            const h = horaSelecionada();
            if (h && srv) {
                const [hh, mm] = h.split(":").map(Number);
                const fimMin = hh * 60 + mm + Number(srv.dataset.duracao);
                const fH = String(Math.floor(fimMin / 60)).padStart(2, "0");
                const fM = String(fimMin % 60).padStart(2, "0");
                resData.textContent = `${dataStr} · ${h}–${fH}:${fM}`;
            } else {
                resData.textContent = dataStr;
            }
        }

        async function carregarPets(tutorId, petIdPre) {
            selPet.innerHTML = '<option value="">Carregando...</option>';
            inpPorte.value = "";
            if (!tutorId) {
                selPet.innerHTML = '<option value="">Selecione primeiro o tutor...</option>';
                atualizarResumo();
                return;
            }
            try {
                const resp = await fetch(`/api/tutores/${tutorId}/pets`);
                const data = await resp.json();
                selPet.innerHTML = "";
                if (!data.pets || data.pets.length === 0) {
                    selPet.innerHTML = '<option value="">Nenhum pet vinculado a este tutor</option>';
                } else {
                    data.pets.forEach((p, idx) => {
                        const opt = document.createElement("option");
                        opt.value = p.id;
                        opt.textContent = `${p.nome} (${p.porte}${p.raca ? " · " + p.raca : ""})`;
                        opt.dataset.nome = p.nome;
                        opt.dataset.porte = p.porte;
                        if ((petIdPre && String(p.id) === String(petIdPre)) || (!petIdPre && idx === 0)) {
                            opt.selected = true;
                        }
                        selPet.appendChild(opt);
                    });
                }
            } catch (e) {
                selPet.innerHTML = '<option value="">Erro ao carregar pets</option>';
            }
            atualizarResumo();
        }

        async function carregarHorarios() {
            const srv = servicoSelecionado();
            const d = inpData.value;
            if (!srv || !d) {
                slotsWrap.innerHTML = '<p class="text-muted small mb-0">Selecione o serviço e a data para ver os horários livres.</p>';
                atualizarResumo();
                return;
            }
            slotsWrap.innerHTML = '<p class="text-muted small mb-0">Consultando disponibilidade na grade...</p>';
            try {
                const resp = await fetch(`/api/horarios?data=${encodeURIComponent(d)}&servico_id=${encodeURIComponent(srv.value)}`);
                const data = await resp.json();
                slotsWrap.innerHTML = "";
                if (!data.horarios || data.horarios.length === 0) {
                    slotsWrap.innerHTML = '<p class="text-muted small mb-0">Sem horários disponíveis nesta data.</p>';
                    return;
                }
                let marcou = false;
                data.horarios.forEach((slot, i) => {
                    const div = document.createElement("div");
                    div.className = "of-option";
                    const id = `ag_slot_${i}`;
                    const input = document.createElement("input");
                    input.type = "radio";
                    input.name = "hora_inicio";
                    input.id = id;
                    input.value = slot.hora;
                    input.required = true;
                    if (!slot.livre) {
                        input.disabled = true;
                    } else if ((horaPreSelecionada && slot.hora === horaPreSelecionada) || (!horaPreSelecionada && !marcou)) {
                        input.checked = true;
                        marcou = true;
                    }
                    const label = document.createElement("label");
                    label.setAttribute("for", id);
                    label.textContent = slot.hora;
                    if (slot.motivo) label.title = slot.motivo;
                    input.addEventListener("change", atualizarResumo);
                    div.appendChild(input);
                    div.appendChild(label);
                    slotsWrap.appendChild(div);
                });
                horaPreSelecionada = "";
            } catch (e) {
                slotsWrap.innerHTML = '<p class="text-danger small mb-0">Não foi possível consultar os horários.</p>';
            }
            atualizarResumo();
        }

        selTutor.addEventListener("change", () => carregarPets(selTutor.value));
        selPet.addEventListener("change", atualizarResumo);
        inpData.addEventListener("change", carregarHorarios);
        inpValor.addEventListener("input", atualizarResumo);

        modalEl.querySelectorAll('input[name="servico_id"]').forEach((r) => {
            r.addEventListener("change", () => {
                inpValor.value = Number(r.dataset.valor).toFixed(2).replace(".", ",");
                carregarHorarios();
            });
        });

        // Abertura do modal via botao de slot livre ou de perfil de tutor
        modalEl.addEventListener("show.bs.modal", (ev) => {
            const btn = ev.relatedTarget;
            if (btn) {
                if (btn.dataset.hora) horaPreSelecionada = btn.dataset.hora;
                if (btn.dataset.data) inpData.value = btn.dataset.data;
                if (btn.dataset.tutorId) {
                    selTutor.value = btn.dataset.tutorId;
                    carregarPets(btn.dataset.tutorId, btn.dataset.petId || "");
                }
            }
            const srv = servicoSelecionado();
            if (srv && !inpValor.value) {
                inpValor.value = Number(srv.dataset.valor).toFixed(2).replace(".", ",");
            }
            if (selTutor.value && selPet.options.length <= 1) {
                carregarPets(selTutor.value);
            }
            carregarHorarios();
        });
    }

    // --- Modal de Baixa / Registrar Pagamento ------------------------------
    function iniciarModalPagamento() {
        const modalEl = document.getElementById("modalPagamento");
        if (!modalEl) return;

        const form = modalEl.querySelector("form");
        const nomePet = document.getElementById("pg_pet_nome");
        const inicialPet = document.getElementById("pg_pet_inicial");
        const infoTutor = document.getElementById("pg_tutor_data");
        const nomeServico = document.getElementById("pg_servico_nome");
        const valorServico = document.getElementById("pg_servico_valor");
        const totalResumo = document.getElementById("pg_total_resumo");
        const totalGrande = document.getElementById("pg_total_grande");
        const inpValor = document.getElementById("pg_valor_pago");
        const boxPix = document.getElementById("pg_pix_box");

        modalEl.addEventListener("show.bs.modal", (ev) => {
            const btn = ev.relatedTarget;
            if (!btn) return;
            const id = btn.dataset.agendamentoId;
            const pet = btn.dataset.pet || "";
            const tutor = btn.dataset.tutor || "";
            const data = btn.dataset.data || "";
            const servico = btn.dataset.servico || "";
            const valor = btn.dataset.valor || "0.00";

            form.action = `/agendamentos/${id}/pagamento`;
            nomePet.textContent = pet;
            inicialPet.textContent = (pet.trim()[0] || "P").toUpperCase();
            infoTutor.textContent = `${tutor} · ${data}`;
            nomeServico.textContent = servico;
            valorServico.textContent = formatarMoeda(valor);
            totalResumo.textContent = formatarMoeda(valor);
            totalGrande.textContent = formatarMoeda(valor);
            inpValor.value = Number(valor).toFixed(2).replace(".", ",");
        });

        inpValor.addEventListener("input", () => {
            totalGrande.textContent = formatarMoeda(inpValor.value);
        });

        modalEl.querySelectorAll('input[name="forma_pagamento"]').forEach((r) => {
            r.addEventListener("change", () => {
                if (boxPix) boxPix.hidden = r.value !== "PIX";
            });
        });

        const btnCopiar = document.getElementById("btn_copiar_pix");
        if (btnCopiar) {
            btnCopiar.addEventListener("click", () => {
                const chave = "petshopolivers@pix.com";
                if (navigator.clipboard) navigator.clipboard.writeText(chave);
                btnCopiar.innerHTML = '<i class="bi bi-check-lg" aria-hidden="true"></i> Chave PIX copiada!';
                setTimeout(() => {
                    btnCopiar.innerHTML = '<i class="bi bi-clipboard" aria-hidden="true"></i> Copiar chave PIX';
                }, 2000);
            });
        }
    }

    // --- Modal de Aviso por WhatsApp (RF15) --------------------------------
    function iniciarModalWhatsapp() {
        const modalEl = document.getElementById("modalWhatsapp");
        if (!modalEl) return;

        const elPet = document.getElementById("wa_pet_titulo");
        const elTutor = document.getElementById("wa_tutor_nome");
        const elInic = document.getElementById("wa_pet_inicial");
        const txtMsg = document.getElementById("wa_mensagem_texto");
        const linkEnviar = document.getElementById("wa_btn_enviar");
        let dados = {};

        function montarMensagem(estilo) {
            const { tutor, pet, servico, valor, hora } = dados;
            if (estilo === "formal") {
                return `Olá, ${tutor}! O atendimento de ${servico} do(a) ${pet} foi finalizado e ele(a) já está pronto(a) para retirada no Pet Shop Oliver's. Valor do atendimento: ${valor}.`;
            }
            if (estilo === "curto") {
                return `Olá, ${tutor}! O(a) ${pet} (${servico}) já está pronto(a) para retirada no Pet Shop Oliver's. Valor: ${valor}.`;
            }
            if (estilo === "lembrete") {
                return `Olá, ${tutor}! Lembramos do agendamento de ${servico} do(a) ${pet} às ${hora} no Pet Shop Oliver's.`;
            }
            return `Olá, ${tutor}! O atendimento de ${servico} do(a) ${pet} foi finalizado e ele(a) já está pronto(a) para retirada no Pet Shop Oliver's.\n\nValor do serviço: ${valor}. Aceitamos PIX, cartão e dinheiro.`;
        }

        function atualizarLink() {
            const tel = (dados.telefone || "").replace(/\D/g, "");
            linkEnviar.href = `https://wa.me/55${tel}?text=${encodeURIComponent(txtMsg.value)}`;
        }

        modalEl.addEventListener("show.bs.modal", (ev) => {
            const btn = ev.relatedTarget;
            if (!btn) return;
            dados = {
                pet: btn.dataset.pet || "",
                tutor: btn.dataset.tutor || "",
                telefone: btn.dataset.telefone || "",
                servico: btn.dataset.servico || "",
                valor: btn.dataset.valorFormatado || "",
                hora: btn.dataset.hora || "",
            };
            elPet.textContent = `${dados.pet} · ${dados.servico}`;
            elTutor.textContent = `${dados.tutor} · ${dados.telefone}`;
            elInic.textContent = (dados.pet.trim()[0] || "P").toUpperCase();
            txtMsg.value = montarMensagem("padrao");
            atualizarLink();
        });

        modalEl.querySelectorAll("[data-wa-modelo]").forEach((b) => {
            b.addEventListener("click", () => {
                txtMsg.value = montarMensagem(b.dataset.waModelo);
                atualizarLink();
            });
        });
        txtMsg.addEventListener("input", atualizarLink);
    }

    // --- Modal de Historico do Pet (RF18) ----------------------------------
    function iniciarModalHistoricoPet() {
        const modalEl = document.getElementById("modalHistoricoPet");
        if (!modalEl) return;

        modalEl.addEventListener("show.bs.modal", async (ev) => {
            const btn = ev.relatedTarget;
            if (!btn || !btn.dataset.petId) return;
            const tbody = document.getElementById("hp_tbody");
            document.getElementById("hp_nome").textContent = btn.dataset.petNome || "Pet";
            document.getElementById("hp_inicial").textContent = ((btn.dataset.petNome || "P")[0]).toUpperCase();
            tbody.innerHTML = '<tr><td colspan="4" class="text-muted">Carregando histórico...</td></tr>';

            try {
                const resp = await fetch(`/api/pets/${btn.dataset.petId}/historico`);
                const data = await resp.json();
                document.getElementById("hp_nome").textContent = data.pet.nome;
                document.getElementById("hp_meta").textContent = `${data.pet.raca} · Porte ${data.pet.porte}`;
                document.getElementById("hp_tutor").textContent = data.pet.tutor;
                document.getElementById("hp_obs").textContent = data.pet.observacoes || "Nenhuma observação registrada.";
                document.getElementById("hp_qtd").textContent = data.estatisticas.atendimentos;
                document.getElementById("hp_total").textContent = data.estatisticas.total;

                if (!data.historico || data.historico.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="4" class="text-muted">Nenhum atendimento registrado para este pet.</td></tr>';
                    return;
                }
                tbody.innerHTML = "";
                data.historico.forEach((h) => {
                    const tr = document.createElement("tr");
                    tr.innerHTML = `
                        <td>${h.data} <span class="text-muted small">${h.hora}</span></td>
                        <td class="fw-semibold">${h.servico}</td>
                        <td class="fw-bold">${h.valor}${h.forma ? ` <span class="text-muted small">(${h.forma})</span>` : ""}</td>
                        <td><span class="of-badge ${h.status_classe}"><i class="bi ${h.status_icone}" aria-hidden="true"></i> ${h.status_texto}</span></td>
                    `;
                    tbody.appendChild(tr);
                });
            } catch (e) {
                tbody.innerHTML = '<tr><td colspan="4" class="text-danger">Erro ao carregar o histórico.</td></tr>';
            }
        });
    }

    // --- Edicao de Pet / Servico / Usuario via modal -----------------------
    function iniciarModaisEdicao() {
        const modalPet = document.getElementById("modalEditarPet");
        if (modalPet) {
            modalPet.addEventListener("show.bs.modal", (ev) => {
                const b = ev.relatedTarget;
                if (!b) return;
                modalPet.querySelector("form").action = `/pets/${b.dataset.petId}/editar`;
                document.getElementById("ep_nome").value = b.dataset.nome || "";
                document.getElementById("ep_porte").value = b.dataset.porte || "Pequeno";
                document.getElementById("ep_raca").value = b.dataset.raca || "";
                document.getElementById("ep_observacoes").value = b.dataset.observacoes || "";
            });
        }

        const modalSrv = document.getElementById("modalEditarServico");
        if (modalSrv) {
            modalSrv.addEventListener("show.bs.modal", (ev) => {
                const b = ev.relatedTarget;
                if (!b) return;
                modalSrv.querySelector("form").action = `/servicos/${b.dataset.id}/editar`;
                document.getElementById("es_nome").value = b.dataset.nome || "";
                document.getElementById("es_duracao").value = b.dataset.duracao || "";
                document.getElementById("es_valor").value = b.dataset.valor || "";
            });
        }

        const modalUsr = document.getElementById("modalEditarUsuario");
        if (modalUsr) {
            modalUsr.addEventListener("show.bs.modal", (ev) => {
                const b = ev.relatedTarget;
                if (!b) return;
                modalUsr.querySelector("form").action = `/usuarios/${b.dataset.id}/editar`;
                document.getElementById("eu_nome").value = b.dataset.nome || "";
                document.getElementById("eu_login").value = b.dataset.login || "";
                document.getElementById("eu_perfil").value = b.dataset.perfil || "Atendente";
                document.getElementById("eu_senha").value = "";
            });
        }
    }

    // --- Filtro instantaneo na tabela de colaboradores ---------------------
    function iniciarFiltroEquipe() {
        const inp = document.getElementById("filtro_equipe");
        const tabela = document.getElementById("tabela_equipe");
        if (!inp || !tabela) return;
        inp.addEventListener("input", () => {
            const termo = inp.value.trim().toLowerCase();
            tabela.querySelectorAll("tbody tr").forEach((tr) => {
                tr.hidden = termo && !tr.textContent.toLowerCase().includes(termo);
            });
        });
    }

    document.addEventListener("DOMContentLoaded", () => {
        document.querySelectorAll('input[data-mask="telefone"]').forEach(aplicarMascaraTelefone);
        iniciarModalAgendamento();
        iniciarModalPagamento();
        iniciarModalWhatsapp();
        iniciarModalHistoricoPet();
        iniciarModaisEdicao();
        iniciarFiltroEquipe();
    });
})();
